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
import random
import shutil
import socket
import subprocess
import sys
import traceback
import traceback
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Optional imports — server_handler requires these, but fail gracefully if missing
try:
    import psutil
except ImportError:
    psutil = None

try:
    import firebase_admin
    from firebase_admin import firestore
except ImportError:
    firebase_admin = None
    firestore = None

try:
    import bridge_server
    from bridge_server import (
        LogStore, init_firestore, _to_ms,
        check_study_experiment, STUDIES_COLLECTION,
    )
except ImportError:
    bridge_server = None
    LogStore = None

try:
    import websockets
except ImportError:
    websockets = None

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
    if psutil is None:
        return 0.0, 0.0
    return psutil.cpu_percent(interval=None), psutil.virtual_memory().percent


# ── Firestore helpers ────────────────────────────────────────────────────────

def _firestore_client():
    """Return a Firestore client (requires firebase_admin initialized)."""
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
                 study_filter: str = "", description: str = "",
                 workers: int = 1):
        self.server_id = name
        self._heartbeat_interval = heartbeat_interval
        self._poll_interval = poll_interval
        self._log_dir = os.path.abspath(log_dir)
        self._render_port = render_port
        self._funnel = funnel
        self._study_filter = study_filter
        self._description = description
        self._max_workers = max(1, workers)

        self._active_jobs: set = set()
        self._jobs_completed: int = 0
        self._gpu_cache: tuple[Optional[float], Optional[float]] = (None, None)
        self._gpu_cache_age: int = 999
        self._render_relay = None
        self._funnel_url: Optional[str] = None
        self._shutting_down = False

    # ── Registration ─────────────────────────────────────────────────

    async def register(self):
        """Register this server in Firestore (auto-register on heartbeat)."""
        from version import get_version
        hostname = socket.gethostname()
        cpu_percent, mem_percent = _get_cpu_mem()
        gpu, gpu_mem = _get_gpu_stats()
        doc = {
            "name": self.server_id,
            "hostname": hostname,
            "description": self._description,
            "version": get_version(),
            "status": "online",
            "last_seen": datetime.now(timezone.utc),
            "heartbeat_interval_sec": self._heartbeat_interval,
            "cpu_percent": cpu_percent,
            "memory_percent": mem_percent,
            "gpu_percent": gpu,
            "gpu_mem_percent": gpu_mem,
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "active_job_ids": [],
            "max_workers": self._max_workers,
            "jobs_completed": 0,
            "render_active": False,
            "funnel_url": None,
        }
        # timeout=15 — a hung RPC must not stall startup for the default
        # 60s+retries window; the heartbeat re-posts this doc every beat.
        _servers_col().document(self.server_id).set(doc, merge=True, timeout=15.0)
        print(f"[ServerHandler] Registered as '{self.server_id}' ({self._max_workers} workers, hostname={hostname})")

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
                    "status": "busy" if self._active_jobs else "online",
                    "last_seen": datetime.now(timezone.utc),
                    "cpu_percent": cpu_percent,
                    "memory_percent": mem_percent,
                    "gpu_percent": self._gpu_cache[0],
                    "gpu_mem_percent": self._gpu_cache[1],
                    "active_job_ids": list(self._active_jobs),
                    "jobs_completed": self._jobs_completed,
                    "render_active": self._render_relay is not None,
                    "funnel_url": self._funnel_url,
                }
                _servers_col().document(self.server_id).set(update, merge=True, timeout=15.0)

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

    async def _maybe_start_render_for_job(self, job_id: str):
        """Start the render relay (+funnel) if the dashboard requested it.

        The dashboard sets render_requested=true on the job; the server
        starts the relay, publishes the URL back to the job doc, and
        clears the flag. Called from the tail loop and before each trial,
        so a request made mid-job takes effect for the next trial (the
        engine attaches its RenderClient at trial start)."""
        try:
            job_ref = _jobs_col().document(job_id)
            job_doc = job_ref.get()
            if not job_doc.exists:
                return
            data = job_doc.to_dict()
            if not data.get("render_requested"):
                return
            if self._render_relay is None:
                await self._start_render_relay()
            if self._funnel and not self._funnel_url:
                await self._start_funnel()
            job_ref.update({
                "render_requested": firestore.DELETE_FIELD,
                "render": {
                    "active": True,
                    "url": self._funnel_url,
                    "port": self._render_port,
                },
                "updated_at": datetime.now(timezone.utc),
            })
            print(f"[ServerHandler] Render exposed for job {job_id}: "
                  f"url={self._funnel_url or 'none (direct ws only)'}")
        except Exception as e:
            print(f"[ServerHandler] Render request handling failed: {e}")

    # ── Job processing ───────────────────────────────────────────────

    async def recover_stale_jobs(self):
        """On startup, reset any jobs stuck in 'claimed' or 'running' from a crash."""
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

    async def recover_stale_trials(self):
        """On startup, reset 'running' trials claimed more than 30 min ago."""
        try:
            db = _firestore_client()
            cutoff = datetime.now(timezone.utc)
            for study_doc in db.collection(STUDIES_COLLECTION).stream():
                for exp_doc in study_doc.reference.collection("experiments").stream():
                    data = exp_doc.to_dict()
                    claimed = dict(data.get("trial_claimed_at") or {})
                    trials = list(data.get("trials") or [])
                    changed = False
                    for idx_str, ts_str in list(claimed.items()):
                        try:
                            idx = int(idx_str)
                            ts = datetime.fromisoformat(ts_str)
                        except (ValueError, TypeError):
                            continue
                        if ((cutoff - ts).total_seconds() > 1800
                                and idx < len(trials) and trials[idx] == "running"):
                            trials[idx] = "pending"
                            del claimed[idx_str]
                            changed = True
                    if changed:
                        exp_doc.reference.update({
                            "trials": trials,
                            "trial_claimed_at": claimed,
                        })
                        print(f"[ServerHandler] Recovered stale trials on "
                              f"{study_doc.id}/{exp_doc.id}")
        except Exception as e:
            print(f"[ServerHandler] Stale trial recovery failed: {e}")

    async def _job_worker(self):
        """Single worker: poll, claim, run, repeat."""
        while not self._shutting_down:
            if len(self._active_jobs) >= self._max_workers:
                await asyncio.sleep(self._poll_interval)
                continue

            job_id = None
            try:
                jobs_col = _jobs_col()
                query = jobs_col.where(filter=firestore.FieldFilter("status", "==", "queued")) \
                    .order_by("created_at").limit(1)
                results = list(query.stream())
                if not results:
                    await asyncio.sleep(self._poll_interval)
                    continue

                job_doc = results[0]
                job = job_doc.to_dict()
                job_id = job_doc.id

                if self._study_filter and job.get("study_id") != self._study_filter:
                    await asyncio.sleep(self._poll_interval)
                    continue

                created_by = job.get("created_by", "")
                if created_by:
                    user_doc = _users_col().document(created_by).get()
                    if not user_doc.exists or not user_doc.to_dict().get("can_run_experiments"):
                        job_doc.reference.update({
                            "status": "failed",
                            "error": "permission denied",
                            "finished_at": datetime.now(timezone.utc),
                        })
                        print(f"[ServerHandler] Job {job_id}: permission denied")
                        continue

                study_id = job.get("study_id", "")
                exp_code = job.get("experiment_code", "")
                if study_id and exp_code:
                    if not check_study_experiment(study_id, exp_code):
                        job_doc.reference.update({
                            "status": "failed",
                            "error": "study/experiment not found",
                            "finished_at": datetime.now(timezone.utc),
                        })
                        continue

                db = _firestore_client()

                @firestore.transactional
                def _claim_txn(txn, ref):
                    snap = ref.get(transaction=txn)
                    if not snap.exists: return False
                    if snap.to_dict().get("status") != "queued": return False
                    txn.update(ref, {"status": "claimed",
                                     "claimed_by": self.server_id,
                                     "claimed_at": datetime.now(timezone.utc)})
                    return True

                if not _claim_txn(db.transaction(), job_doc.reference):
                    await asyncio.sleep(self._poll_interval)
                    continue

                self._active_jobs.add(job_id)
                print(f"[ServerHandler] Claimed job {job_id}: {study_id}/{exp_code}")

                job_doc.reference.update({
                    "status": "running",
                    "started_at": datetime.now(timezone.utc),
                })

                result = await self._run_job(job_id, job)

                # A trial that crashed is a job failure — don't report
                # "completed" when trials errored.  Per-trial status lives
                # on the experiment doc (trial_errors); the job error shows
                # the first traceback so the dashboard lists it right away.
                failed = result.get("failed_trials", 0)
                update = {
                    "status": "failed" if failed else "completed",
                    "result": result,
                    "finished_at": datetime.now(timezone.utc),
                }
                if failed:
                    update["error"] = result.get("error", "")
                job_doc.reference.update(update)
                self._jobs_completed += 1
                verdict = f"failed ({failed} trial{'s' if failed != 1 else ''})" \
                    if failed else f"completed ({result.get('trials_completed', 0)} trials)"
                print(f"[ServerHandler] Job {job_id} {verdict}")
                self._log_usage(job_id, job, result)

            except Exception:
                trace = traceback.format_exc()
                print(f"[ServerHandler] Job error: {trace}")
                if job_id:
                    try:
                        _jobs_col().document(job_id).update({
                            "status": "failed", "error": trace,
                            "finished_at": datetime.now(timezone.utc),
                        })
                    except Exception: pass
            finally:
                if job_id:
                    self._active_jobs.discard(job_id)
                await asyncio.sleep(self._poll_interval)

    async def job_loop(self):
        """Spawn N workers to process jobs concurrently."""
        await self.recover_stale_jobs()
        await self.recover_stale_trials()
        tasks = [asyncio.create_task(self._job_worker())
                 for _ in range(self._max_workers)]
        print(f"[ServerHandler] {self._max_workers} job workers started")
        for t in tasks:
            try: await t
            except asyncio.CancelledError: pass

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
                "trial_count": result.get("trials_completed", 0),
                "status": "completed",
            })
        except Exception:
            pass

    async def _run_job(self, job_id: str, job: dict) -> dict:
        """Process a job by claiming and running individual trials (one game each).

        The experiment doc holds a ``trials`` array of per-index statuses.
        Each worker claims a random pending index via a Firestore transaction
        (auto-retried on contention), waits 0-5s, then runs ONE game for it.
        """
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

        config_data = job.get("config", {})  # fallback for old jobs
        config_path = f"{STUDIES_COLLECTION}/{study_id}/experiments/{exp_code}"
        if study_id and exp_code:
            try:
                db = _firestore_client()
                exp_doc = db.collection(STUDIES_COLLECTION).document(study_id) \
                          .collection("experiments").document(exp_code).get()
                if exp_doc.exists:
                    stored = exp_doc.to_dict().get("config")
                    if stored:
                        config_data = stored
                        keys = ",".join(sorted(stored.keys())) if isinstance(stored, dict) else "?"
                        print(f"[ServerHandler] Loaded config from {config_path}: "
                              f"{stored.get('type', '?')}::{stored.get('class', '?')} "
                              f"trial_count={stored.get('trial_count')} keys=[{keys}]")
                    else:
                        print(f"[ServerHandler] Experiment doc has no 'config' field: {config_path}")
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

        trial_count = exp.trial_count or 1
        exp_ref = _firestore_client().collection(STUDIES_COLLECTION) \
                  .document(study_id).collection("experiments").document(exp_code)

        # Ensure the trials array exists and matches the config's trial_count
        await self._init_trials(exp_ref, trial_count)

        # ── Bridge (push games + stats to Firestore) ──────────
        if bridge_server and not bridge_server._firestore_ready:
            init_firestore()

        store = LogStore(job_log_dir)
        store.load_logs()

        async def _tail_loop():
            last_game_count = 0
            while not self._shutting_down:
                try:
                    await self._maybe_start_render_for_job(job_id)
                    store.tail()
                    if len(store.games) > last_game_count:
                        last_game_count = len(store.games)
                        try:
                            _jobs_col().document(job_id).update({
                                "result": {"trials_completed": last_game_count,
                                           "trial_count": trial_count},
                                "updated_at": datetime.now(timezone.utc),
                            })
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[ServerHandler] Tail/push error: {e}")
                await asyncio.sleep(5.0)

        tail_task = asyncio.create_task(_tail_loop())

        # ── Trial loop ─────────────────────────────────────────
        trials_done = 0
        failed_trials = 0
        first_error = ""
        try:
            while not self._shutting_down:
                # Random 0-5s wait to mitigate multi-server collisions
                await asyncio.sleep(random.uniform(0, 5))

                trial_index = await self._claim_trial(exp_ref)
                if trial_index is None:
                    break  # no pending trials left

                # Start the relay BEFORE the trial engine is created so the
                # engine attaches a RenderClient from the first tick.
                await self._maybe_start_render_for_job(job_id)

                print(f"[ServerHandler] Job {job_id}: running trial {trial_index}")
                os.environ["TRIAL_INDEX"] = str(trial_index)

                ok, err_msg = await self._run_trial(
                    job_id, trial_index, config_data, config,
                    free_roam, voting, win_conditions, position_mode,
                    map_data, agent_types, exp, job_log_dir)
                if not ok:
                    failed_trials += 1
                    if not first_error:
                        first_error = err_msg
                await self._finish_trial(exp_ref, trial_index, ok, err_msg)
                trials_done += 1

                try:
                    _jobs_col().document(job_id).update({
                        "result": {"trials_completed": trials_done,
                                   "trial_count": trial_count,
                                   "failed_trials": failed_trials},
                        "updated_at": datetime.now(timezone.utc),
                    })
                except Exception:
                    pass

            return {"trials_completed": trials_done, "trial_count": trial_count,
                    "failed_trials": failed_trials, "error": first_error}
        finally:
            os.environ.pop("TRIAL_INDEX", None)
            tail_task.cancel()
            try:
                store.tail()  # final flush
            except Exception:
                pass

    # ── Trial claiming / finishing ────────────────────────────────

    async def _init_trials(self, exp_ref, trial_count: int):
        """Ensure the experiment doc has a trials array of the right length."""
        db = _firestore_client()

        @firestore.transactional
        def _txn(txn, ref):
            snap = ref.get(transaction=txn)
            if not snap.exists:
                return
            trials = list(snap.to_dict().get("trials") or [])
            if len(trials) != trial_count:
                if len(trials) < trial_count:
                    trials.extend(["pending"] * (trial_count - len(trials)))
                else:
                    trials = trials[:trial_count]
                txn.update(ref, {"trials": trials})
        try:
            _txn(db.transaction(), exp_ref)
        except Exception as e:
            print(f"[ServerHandler] init_trials failed: {e}")

    async def _claim_trial(self, exp_ref) -> Optional[int]:
        """Atomically claim a random pending trial index.

        Firestore auto-retries the transaction on contention; each retry
        re-reads the fresh trials array and picks a NEW random index.
        Returns None if no pending trials remain.
        """
        db = _firestore_client()

        @firestore.transactional
        def _txn(txn, ref):
            snap = ref.get(transaction=txn)
            if not snap.exists:
                return None
            data = snap.to_dict()
            trials = list(data.get("trials") or [])
            pending = [i for i, s in enumerate(trials) if s == "pending"]
            if not pending:
                return None
            idx = random.choice(pending)
            trials[idx] = "running"
            now_iso = datetime.now(timezone.utc).isoformat()
            claimed_at = dict(data.get("trial_claimed_at") or {})
            claimed_at[str(idx)] = now_iso
            claimed_by = dict(data.get("trial_claimed_by") or {})
            claimed_by[str(idx)] = self.server_id
            txn.update(ref, {
                "trials": trials,
                "trial_claimed_at": claimed_at,
                "trial_claimed_by": claimed_by,
            })
            return idx

        try:
            return _txn(db.transaction(), exp_ref)
        except Exception as e:
            print(f"[ServerHandler] Trial claim failed: {e}")
            return None

    async def _finish_trial(self, exp_ref, trial_index: int, success: bool,
                            error_msg: str = ""):
        """Mark a claimed trial as completed, or as error with a message."""
        db = _firestore_client()

        @firestore.transactional
        def _txn(txn, ref):
            snap = ref.get(transaction=txn)
            if not snap.exists:
                return
            data = snap.to_dict()
            trials = list(data.get("trials") or [])
            # If the data was cleared after this trial was claimed, the
            # result belongs to a wiped run — discard it, don't resurrect.
            # (Clear deletes trial_claimed_at, so a missing claim entry
            # alongside a cleared_at also means the claim predates the clear.)
            idx_str = str(trial_index)
            cleared = data.get("cleared_at")
            claimed = (data.get("trial_claimed_at") or {}).get(idx_str)
            if cleared is not None and (claimed is None or _to_ms(cleared) > _to_ms(claimed)):
                print(f"[ServerHandler] Trial {trial_index} claimed before clear — discarding result")
                return
            updates = {}
            if trial_index < len(trials):
                trials[trial_index] = "completed" if success else "error"
                updates["trials"] = trials
            # Clear the claim timestamp
            claimed = dict(data.get("trial_claimed_at") or {})
            if idx_str in claimed:
                del claimed[idx_str]
                updates["trial_claimed_at"] = claimed
            # Record completion metadata: server, time, version
            now_iso = datetime.now(timezone.utc).isoformat()
            completed_at = dict(data.get("trial_completed_at") or {})
            completed_at[idx_str] = now_iso
            updates["trial_completed_at"] = completed_at
            completed_by = dict(data.get("trial_completed_by") or {})
            completed_by[idx_str] = self.server_id
            updates["trial_completed_by"] = completed_by
            from version import get_version
            versions = dict(data.get("trial_versions") or {})
            versions[idx_str] = get_version()
            updates["trial_versions"] = versions
            errors = dict(data.get("trial_errors") or {})
            if success:
                # A successful rerun must not leave a stale error behind
                if idx_str in errors:
                    del errors[idx_str]
                    updates["trial_errors"] = errors
            else:
                # Room for a full traceback (message + file/line frames)
                errors[idx_str] = error_msg[:4000]
                updates["trial_errors"] = errors
            if updates:
                txn.update(ref, updates)
        try:
            _txn(db.transaction(), exp_ref)
        except Exception as e:
            print(f"[ServerHandler] finish_trial failed: {e}")

    async def _run_trial(self, job_id: str, trial_index: int, config_data: dict,
                         config, free_roam, voting, win_conditions,
                         position_mode, map_data, agent_types, exp,
                         job_log_dir: str) -> tuple[bool, str]:
        """Run ONE game for the claimed trial. Returns (success, error_msg)."""
        from engine import GameEngine
        from event_store import EventStore

        # Write to the job-level dir — sessions are timestamped, so
        # sequential trials never collide.  LogStore tails SESSION-*.jsonl
        # at the top level, so subdirectories would be invisible to it.
        event_store = EventStore(log_dir=job_log_dir)

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
        engine._experiment_config = config_data
        engine.game = exp

        try:
            summary = await engine.run(max_games=1)
            print(f"[ServerHandler] Trial {trial_index} done: "
                  f"{json.dumps(summary or {})[:200]}")
            return True, ""
        except Exception as e:
            # Full traceback → console AND stored on the experiment doc so
            # the exact file/line is visible in the dashboard, not just
            # the bare exception message.
            tb = traceback.format_exc()
            print(f"[ServerHandler] Trial {trial_index} failed: {e}\n{tb}")
            return False, f"{e}\n{tb}"

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

        # Fail all active jobs
        for job_id in list(self._active_jobs):
            try:
                _jobs_col().document(job_id).update({
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
    parser.add_argument("--description", default="",
                        help="Human-readable description of this server")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of concurrent job workers (default: 1)")
    args = parser.parse_args()

    # ── Init Firestore ────────────────────────────────────────
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
        description=args.description,
        workers=args.workers,
    )

    # Registration is best-effort: the heartbeat loop re-posts the server
    # doc every beat, so a transient Firestore timeout here (e.g. 504
    # Deadline Exceeded) must NOT kill the daemon — jobs and heartbeats
    # should keep running regardless.
    try:
        await handler.register()
    except Exception as e:
        print(f"[ServerHandler] Registration failed: {e}")
        traceback.print_exc()
        print("[ServerHandler] Continuing — heartbeat will keep retrying registration.")

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
