#!/usr/bin/env python3
"""server_handler.py — Server daemon that listens for experiment jobs and runs them.

Registers with Firestore on startup, sends heartbeats with CPU/memory/GPU
stats, polls the jobs collection for queued work, and runs one job at a time.

Usage:
    python server_handler.py [--name my-server] [--heartbeat-interval 30]
                             [--poll-interval 5] [--render] [--funnel]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_gpu_stats() -> tuple[Optional[float], Optional[float]]:
    """Return (gpu_percent, gpu_mem_percent) or (None, None) if no GPU."""
    if not shutil.which("nvidia-smi"):
        return None, None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            text=True, timeout=5,
        ).strip()
        parts = out.split(",")
        if len(parts) >= 3:
            util = float(parts[0].strip())
            mem_used = float(parts[1].strip())
            mem_total = float(parts[2].strip())
            mem_pct = (mem_used / mem_total * 100) if mem_total > 0 else 0.0
            return util, mem_pct
    except Exception:
        pass
    return None, None


def _get_cpu_mem() -> tuple[float, float]:
    """Return (cpu_percent, memory_percent)."""
    import psutil
    return psutil.cpu_percent(interval=None), psutil.virtual_memory().percent


# ── Firestore helpers ────────────────────────────────────────────────────────

def _firestore_client():
    """Return a Firestore client (requires firebase_admin initialized)."""
    import firebase_admin
    from firebase_admin import firestore
    return firestore.client()


def _servers_col():
    return _firestore_client().collection("servers")


def _jobs_col():
    return _firestore_client().collection("jobs")


def _users_col():
    return _firestore_client().collection("users")


# ── Server Handler ───────────────────────────────────────────────────────────


class ServerHandler:
    """Main server daemon: register, heartbeat, poll jobs, run engine."""

    def __init__(self, name: str, heartbeat_interval: float = 30.0,
                 poll_interval: float = 5.0, log_dir: str = "../log",
                 render_port: int = 8081, funnel: bool = False,
                 study_filter: str = ""):
        self.server_id = name
        self._heartbeat_interval = heartbeat_interval
        self._poll_interval = poll_interval
        self._log_dir = os.path.abspath(log_dir)
        self._render_port = render_port
        self._funnel = funnel
        self._study_filter = study_filter

        self._current_job_id: Optional[str] = None
        self._jobs_completed: int = 0
        self._gpu_cache: tuple[Optional[float], Optional[float]] = (None, None)
        self._gpu_cache_age: int = 999
        self._render_relay = None
        self._funnel_url: Optional[str] = None
        self._shutting_down = False

    # ── Registration ─────────────────────────────────────────────────

    async def register(self):
        """Register this server in Firestore (auto-register on heartbeat)."""
        import psutil
        hostname = socket.gethostname()
        cpu_percent, mem_percent = _get_cpu_mem()
        gpu, gpu_mem = _get_gpu_stats()
        doc = {
            "name": self.server_id,
            "hostname": hostname,
            "status": "online",
            "last_seen": datetime.now(timezone.utc),
            "heartbeat_interval_sec": self._heartbeat_interval,
            "cpu_percent": cpu_percent,
            "memory_percent": mem_percent,
            "gpu_percent": gpu,
            "gpu_mem_percent": gpu_mem,
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "current_job_id": None,
            "jobs_completed": 0,
            "render_active": False,
            "funnel_url": None,
            "version": "1.0",
        }
        _servers_col().document(self.server_id).set(doc, merge=True)
        print(f"[ServerHandler] Registered as '{self.server_id}' (hostname={hostname})")

    # ── Heartbeat ────────────────────────────────────────────────────

    async def heartbeat_loop(self):
        """Periodically update server doc with system stats."""
        tick = 0
        while not self._shutting_down:
            try:
                cpu_percent, mem_percent = _get_cpu_mem()

                # GPU: cached every 5th heartbeat (subprocess per beat is wasteful)
                tick += 1
                if tick % 5 == 0:
                    self._gpu_cache = _get_gpu_stats()

                update = {
                    "status": "busy" if self._current_job_id else "online",
                    "last_seen": datetime.now(timezone.utc),
                    "cpu_percent": cpu_percent,
                    "memory_percent": mem_percent,
                    "gpu_percent": self._gpu_cache[0],
                    "gpu_mem_percent": self._gpu_cache[1],
                    "current_job_id": self._current_job_id,
                    "jobs_completed": self._jobs_completed,
                    "render_active": self._render_relay is not None,
                    "funnel_url": self._funnel_url,
                }
                _servers_col().document(self.server_id).set(update, merge=True)

                # Append usage sample (rolling, cap at 120)
                self._append_usage_sample(cpu_percent, mem_percent)

            except Exception as e:
                print(f"[ServerHandler] Heartbeat failed: {e}")

            await asyncio.sleep(self._heartbeat_interval)

    def _append_usage_sample(self, cpu: float, mem: float):
        """Append a usage sample to server_usage/{server_id}."""
        try:
            db = _firestore_client()
            usage_ref = db.collection("server_usage").document(self.server_id)
            doc = usage_ref.get()
            samples = []
            if doc.exists:
                samples = doc.to_dict().get("samples", [])

            samples.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "cpu": cpu,
                "mem": mem,
                "gpu": self._gpu_cache[0],
            })
            # Cap at 120 samples (~1 hour @ 30s interval)
            if len(samples) > 120:
                samples = samples[-120:]

            usage_ref.set({
                "server_id": self.server_id,
                "samples": samples,
                "updated_at": datetime.now(timezone.utc),
            }, merge=True)
        except Exception:
            pass  # Usage logging is best-effort

    # ── Render relay ─────────────────────────────────────────────────

    async def _start_render_relay(self):
        """Optionally start the render relay for remote Godot viewing."""
        try:
            from render_relay import RenderRelay
            relay = RenderRelay("0.0.0.0", self._render_port)
            self._render_relay = relay  # store ref for cleanup
            # Start as background task
            import websockets
            async def _serve():
                async with websockets.serve(relay._handler, relay.host, relay.port):
                    print(f"[ServerHandler] Render relay on {relay.host}:{relay.port}")
                    while not self._shutting_down:
                        await asyncio.sleep(1)

            asyncio.create_task(_serve())
            await asyncio.sleep(0.5)  # let the server start
            print(f"[ServerHandler] Render relay started on :{self._render_port}")
        except Exception as e:
            print(f"[ServerHandler] Render relay failed to start: {e}")

    async def _start_funnel(self):
        """Optionally start a Tailscale funnel for the render port."""
        if not shutil.which("tailscale"):
            print("[ServerHandler] tailscale CLI not found — skipping funnel")
            return
        try:
            # Get the Tailscale DNS name
            status = subprocess.check_output(
                ["tailscale", "status", "--json"], text=True, timeout=10
            )
            info = json.loads(status)
            dns_name = info.get("Self", {}).get("DNSName", "")
            if not dns_name:
                print("[ServerHandler] No Tailscale DNS name found — is Tailscale running?")
                return
            self._funnel_url = f"https://{dns_name.rstrip('.')}"
            print(f"[ServerHandler] Tailscale DNS: {dns_name}")

            # Start funnel on the render port
            subprocess.run(
                ["tailscale", "funnel", str(self._render_port)], check=False,
                timeout=15, capture_output=True,
            )
            print(f"[ServerHandler] Tailscale funnel on port {self._render_port} → {self._funnel_url}")
        except Exception as e:
            print(f"[ServerHandler] Tailscale funnel setup failed: {e}")
            self._funnel_url = None

    # ── Job processing ───────────────────────────────────────────────

    async def recover_stale_jobs(self):
        """On startup, reset any jobs stuck in 'claimed' or 'running' from a crash."""
        from firebase_admin import firestore
        try:
            jobs_col = _jobs_col()
            for status in ("claimed", "running"):
                stale = jobs_col.where(filter=firestore.FieldFilter("status", "==", status)) \
                    .where(filter=firestore.FieldFilter("claimed_by", "==", self.server_id)).limit(20).stream()
                for job_doc in stale:
                    data = job_doc.to_dict()
                    claimed_at = data.get("claimed_at")
                    if claimed_at:
                        age = (datetime.now(timezone.utc) - claimed_at).total_seconds()
                        if age > 1800:  # 30 min
                            job_doc.reference.update({
                                "status": "failed",
                                "error": "recovered: server crashed or timed out",
                                "finished_at": datetime.now(timezone.utc),
                            })
                            print(f"[ServerHandler] Recovered stale job {job_doc.id}")
        except Exception as e:
            print(f"[ServerHandler] Stale job recovery failed: {e}")

    async def job_loop(self):
        """Poll for queued jobs and process them one at a time."""
        await self.recover_stale_jobs()

        while not self._shutting_down:
            if self._current_job_id:
                await asyncio.sleep(self._poll_interval)
                continue

            from firebase_admin import firestore
            try:
                jobs_col = _jobs_col()
                # Query oldest queued job
                query = jobs_col.where(filter=firestore.FieldFilter("status", "==", "queued")) \
                    .order_by("created_at").limit(1)
                results = list(query.stream())
                if not results:
                    await asyncio.sleep(self._poll_interval)
                    continue

                job_doc = results[0]
                job = job_doc.to_dict()
                job_id = job_doc.id

                # If study filter is set, skip jobs for other studies
                if self._study_filter and job.get("study_id") != self._study_filter:
                    await asyncio.sleep(self._poll_interval)
                    continue

                # ── Validate ────────────────────────────────────
                created_by = job.get("created_by", "")
                if created_by:
                    user_doc = _users_col().document(created_by).get()
                    if not user_doc.exists or not user_doc.to_dict().get("can_run_experiments"):
                        # Permission denied
                        job_doc.reference.update({
                            "status": "failed",
                            "error": "permission denied: user lacks can_run_experiments flag",
                            "finished_at": datetime.now(timezone.utc),
                        })
                        print(f"[ServerHandler] Job {job_id}: permission denied for user {created_by}")
                        continue

                study_id = job.get("study_id", "")
                exp_code = job.get("experiment_code", "")
                if study_id and exp_code:
                    from bridge_server import check_study_experiment
                    if not check_study_experiment(study_id, exp_code):
                        job_doc.reference.update({
                            "status": "failed",
                            "error": "study/experiment not found in Firestore",
                            "finished_at": datetime.now(timezone.utc),
                        })
                        print(f"[ServerHandler] Job {job_id}: study/experiment not found ({study_id}/{exp_code})")
                        continue

                # ── Claim transactionally ──────────────────────
                # Use a Firestore transaction to atomically claim the job,
                # guarding against two servers racing on the same queued job.
                from firebase_admin import firestore as _fs
                db = _firestore_client()

                @_fs.transactional
                def _claim_txn(txn, ref):
                    snap = ref.get(transaction=txn)
                    if not snap.exists:
                        return False
                    data = snap.to_dict()
                    if data.get("status") != "queued":
                        return False
                    txn.update(ref, {
                        "status": "claimed",
                        "claimed_by": self.server_id,
                        "claimed_at": datetime.now(timezone.utc),
                    })
                    return True

                claimed = _claim_txn(db.transaction(), job_doc.reference)
                if not claimed:
                    continue  # Another server claimed it

                self._current_job_id = job_id
                print(f"[ServerHandler] Claimed job {job_id}: {study_id}/{exp_code}")

                # ── Update to running ─────────────────────────
                job_doc.reference.update({
                    "status": "running",
                    "started_at": datetime.now(timezone.utc),
                })

                # ── Run ───────────────────────────────────────
                result = await self._run_job(job_id, job)

                # ── Report ────────────────────────────────────
                job_doc.reference.update({
                    "status": "completed",
                    "result": result,
                    "finished_at": datetime.now(timezone.utc),
                })
                self._jobs_completed += 1
                print(f"[ServerHandler] Job {job_id} completed: {result.get('games', 0)} games")

                # Log usage
                self._log_usage(job_id, job, result)

            except Exception as e:
                trace = traceback.format_exc()
                print(f"[ServerHandler] Job error: {trace}")
                try:
                    if self._current_job_id:
                        _jobs_col().document(self._current_job_id).update({
                            "status": "failed",
                            "error": trace,
                            "finished_at": datetime.now(timezone.utc),
                        })
                except Exception:
                    pass
            finally:
                self._current_job_id = None

            await asyncio.sleep(self._poll_interval)

    def _log_usage(self, job_id: str, job: dict, result: dict):
        """Log job completion to server_usage collection."""
        try:
            db = _firestore_client()
            usage_id = f"{self.server_id}_{job_id}"
            db.collection("server_usage").document(usage_id).set({
                "server_id": self.server_id,
                "job_id": job_id,
                "user_id": job.get("created_by", ""),
                "study_id": job.get("study_id", ""),
                "experiment_id": job.get("experiment_code", ""),
                "started_at": job.get("started_at"),
                "completed_at": datetime.now(timezone.utc),
                "token_count": 0,  # TODO: extract from trace
                "game_count": result.get("games", 0),
                "status": "completed",
            })
        except Exception:
            pass

    async def _run_job(self, job_id: str, job: dict) -> dict:
        """Run a single experiment job. Returns result summary dict."""
        max_games = job.get("max_games", 1)
        study_id = job.get("study_id", "")
        exp_code = job.get("experiment_code", "")

        # Set env vars so bridge_server.py LogStore uses the right paths
        os.environ["STUDY_ID"] = study_id
        os.environ["EXPERIMENT_CODE"] = exp_code

        # Isolated log dir for this job
        job_log_dir = os.path.join(self._log_dir, job_id)
        os.makedirs(job_log_dir, exist_ok=True)

        # ── Load config from experiment doc ────────────────────
        from experiment import build_experiment_from_dict
        from bridge_server import _firestore_ready, STUDIES_COLLECTION

        config_data = job.get("config", {})  # fallback for old jobs
        config_path = f"{STUDIES_COLLECTION}/{study_id}/experiments/{exp_code}"
        if _firestore_ready and study_id and exp_code:
            from firebase_admin import firestore as _fs
            try:
                db = _fs.client()
                exp_doc = db.collection(STUDIES_COLLECTION).document(study_id) \
                          .collection("experiments").document(exp_code).get()
                if exp_doc.exists:
                    stored = exp_doc.to_dict().get("config")
                    if stored:
                        config_data = stored
                        print(f"[ServerHandler] Loaded config from {config_path}")
                else:
                    print(f"[ServerHandler] Experiment doc not found: {config_path}")
            except Exception as e:
                print(f"[ServerHandler] Could not read {config_path}: {e}")
                # Fall back to config in job doc if present

        if not config_data:
            raise RuntimeError(
                f"No 'config' field on {config_path}. "
                "Dashboard: select the experiment → config tab → edit → save.")

        exp = build_experiment_from_dict(config_data)

        from experiment_runtime import experiment_to_runtime
        config, free_roam, voting, win_conditions, position_mode, map_data, agent_types = \
            experiment_to_runtime(exp)

        # ── Engine ────────────────────────────────────────────
        from engine import GameEngine
        from event_store import EventStore

        event_store = EventStore(log_dir=job_log_dir)
        print(f"[ServerHandler] Job logs: {job_log_dir}")

        render_client = None
        if self._render_relay:
            from render_client import RenderClient
            render_client = RenderClient("localhost", self._render_port)

        engine = GameEngine(config, map_data, event_store, render_client, [],
                            free_roam_phase=free_roam,
                            voting_phase=voting,
                            win_conditions=win_conditions,
                            position_mode=position_mode)
        engine._agent_types = agent_types
        engine._experiment_config = exp.to_json()
        engine.game = exp

        # ── Bridge (push games + stats to Firestore) ──────────
        from bridge_server import LogStore, _firestore_ready, init_firestore
        if not _firestore_ready:
            init_firestore()

        store = LogStore(job_log_dir)
        store.load_logs()

        async def _tail_loop():
            last_game_count = 0
            while not self._shutting_down:
                try:
                    store.tail()
                    # Push partial progress to job doc as games complete
                    if len(store.games) > last_game_count:
                        last_game_count = len(store.games)
                        try:
                            _jobs_col().document(job_id).update({
                                "result": {"games_completed": last_game_count},
                                "updated_at": datetime.now(timezone.utc),
                            })
                        except Exception:
                            pass
                except Exception:
                    pass
                await asyncio.sleep(5.0)

        tail_task = asyncio.create_task(_tail_loop())

        # ── Run ───────────────────────────────────────────────
        try:
            summary = await engine.run(max_games=max_games)
            return summary or {}
        finally:
            tail_task.cancel()
            try:
                store.tail()  # final flush
            except Exception:
                pass

    # ── Shutdown ────────────────────────────────────────────────────

    async def shutdown(self):
        """Graceful shutdown."""
        self._shutting_down = True
        print("[ServerHandler] Shutting down...")

        # Mark server offline
        try:
            _servers_col().document(self.server_id).update({
                "status": "offline",
                "current_job_id": None,
                "last_seen": datetime.now(timezone.utc),
            })
        except Exception:
            pass

        # Fail current job if any
        if self._current_job_id:
            try:
                _jobs_col().document(self._current_job_id).update({
                    "status": "failed",
                    "error": "server shutting down",
                    "finished_at": datetime.now(timezone.utc),
                })
            except Exception:
                pass

        # Stop funnel
        if self._funnel and shutil.which("tailscale"):
            try:
                subprocess.run(
                    ["tailscale", "funnel", "off", str(self._render_port)],
                    timeout=10, capture_output=True,
                )
                print("[ServerHandler] Tailscale funnel stopped")
            except Exception:
                pass

        print("[ServerHandler] Stopped.")


# ── Main ─────────────────────────────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser(description="Among-I Server Handler")
    parser.add_argument("--name", default=socket.gethostname(),
                        help="Server display name (default: hostname)")
    parser.add_argument("--heartbeat-interval", type=float, default=30.0,
                        help="Seconds between heartbeats (default: 30)")
    parser.add_argument("--poll-interval", type=float, default=5.0,
                        help="Seconds between job queue polls (default: 5)")
    parser.add_argument("--render", action="store_true",
                        help="Start render relay for remote Godot viewing")
    parser.add_argument("--render-port", type=int, default=8081)
    parser.add_argument("--funnel", action="store_true",
                        help="Enable Tailscale funnel for render port")
    parser.add_argument("--log-dir", default="../log",
                        help="Log directory for job output (default: ../log)")
    parser.add_argument("--study", default="",
                        help="Optional: only accept jobs for this study ID")
    args = parser.parse_args()

    # ── Init Firestore ────────────────────────────────────────
    from bridge_server import init_firestore
    if not init_firestore():
        print("[ServerHandler] FATAL: Firestore not available. Check FIREBASE_CRED_PATH.")
        return

    handler = ServerHandler(
        name=args.name,
        heartbeat_interval=args.heartbeat_interval,
        poll_interval=args.poll_interval,
        log_dir=args.log_dir,
        render_port=args.render_port,
        funnel=args.funnel,
        study_filter=args.study,
    )

    await handler.register()

    if args.render:
        await handler._start_render_relay()
    if args.funnel:
        await handler._start_funnel()

    heartbeat_task = asyncio.create_task(handler.heartbeat_loop())
    job_task = asyncio.create_task(handler.job_loop())

    try:
        await asyncio.gather(heartbeat_task, job_task)
    except KeyboardInterrupt:
        print("\n[ServerHandler] Interrupted — shutting down...")
    finally:
        await handler.shutdown()




if __name__ == "__main__":
    asyncio.run(main())
