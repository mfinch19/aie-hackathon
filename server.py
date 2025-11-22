import os
import json
import asyncio
import subprocess
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List
import glob
import time

app = FastAPI()

# Enable CORS for React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Log file path
LOG_FILE = "agent_logs.jsonl"

def clear_logs():
    """Clear the log file"""
    with open(LOG_FILE, "w") as f:
        f.write("")

def append_log(log_type: str, message: str, script: str = "system"):
    """Append a log entry to the log file"""
    with open(LOG_FILE, "a", buffering=1) as f:  # line-buffered
        f.write(json.dumps({
            "type": log_type,
            "script": script,
            "message": message,
            "timestamp": time.time()
        }) + "\n")
        f.flush()
        os.fsync(f.fileno())  # extra aggressive: flush OS buffers too



@app.get("/api/logs")
async def get_logs(since: float = 0):
    """Get logs since a given timestamp"""
    print(f"[get_logs] called with since={since}")

    logs = []

    if os.path.exists(LOG_FILE):
        print(f"[get_logs] LOG_FILE exists at {LOG_FILE}")
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            print(f"[get_logs] total lines in log file: {len(lines)}")

            for idx, line in enumerate(lines):
                if line.strip():
                    try:
                        log = json.loads(line)
                        print(f"[get_logs] line {idx}: parsed timestamp {log.get('timestamp')}")

                        if log.get("timestamp") is None:
                            print(f"[get_logs] line {idx}: missing timestamp key")
                            continue

                        if log["timestamp"] > since:
                            print(f"[get_logs] line {idx}: ADDED (timestamp {log['timestamp']} > {since})")
                            logs.append(log)
                        else:
                            print(f"[get_logs] line {idx}: skipped (timestamp {log['timestamp']} <= {since})")
                    except Exception as e:
                        print(f"[get_logs] line {idx} FAILED TO PARSE: {e}")
    else:
        print(f"[get_logs] LOG_FILE does NOT exist at {LOG_FILE}")

    print(f"[get_logs] returning {len(logs)} logs")
    return {"logs": logs}


async def run_script_with_logs(script_name: str, *args):
    """Run a Python script and save its output to log file"""
    process = await asyncio.create_subprocess_exec(
        "python", script_name, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        message = line.decode().strip()
        append_log("log", message, script_name)
    
    await process.wait()
    return process.returncode

@app.post("/api/run/recon")
async def run_recon():
    """Run the QA Agent (Reconnaissance phase)"""
    clear_logs()
    append_log("status", "starting", "recon")
    
    returncode = await run_script_with_logs("qa_agent_v1.py")
    
    append_log("status", "completed" if returncode == 0 else "failed", "recon")
    
    return {"status": "completed" if returncode == 0 else "failed"}

@app.post("/api/run/plan")
async def run_plan():
    """Run the Exploit Planner"""
    await manager.broadcast(json.dumps({
        "type": "status",
        "phase": "plan",
        "status": "starting"
    }))
    
    returncode = await run_script_with_logs("exploit_planner.py")
    
    await manager.broadcast(json.dumps({
        "type": "status",
        "phase": "plan",
        "status": "completed" if returncode == 0 else "failed"
    }))
    
    return {"status": "completed" if returncode == 0 else "failed"}

@app.post("/api/run/attack")
async def run_attack():
    """Run the Attack Execution"""
    await manager.broadcast(json.dumps({
        "type": "status",
        "phase": "attack",
        "status": "starting"
    }))
    
    returncode = await run_script_with_logs("attack.py")
    
    await manager.broadcast(json.dumps({
        "type": "status",
        "phase": "attack",
        "status": "completed" if returncode == 0 else "failed"
    }))
    
    return {"status": "completed" if returncode == 0 else "failed"}

@app.get("/api/vulnerabilities")
async def get_vulnerabilities():
    """Get the list of found vulnerabilities from rl_training_data.json"""
    try:
        if os.path.exists("rl_training_data.json"):
            with open("rl_training_data.json", "r") as f:
                data = json.load(f)
                # Filter for high-reward items
                vulns = [item for item in data if item.get("reward", 0) >= 0.5]
                return {"vulnerabilities": vulns, "total": len(vulns)}
        return {"vulnerabilities": [], "total": 0}
    except Exception as e:
        return {"error": str(e), "vulnerabilities": [], "total": 0}

@app.get("/api/exploits")
async def get_exploits():
    """Get the generated exploit plans"""
    try:
        if os.path.exists("final_exploit_plan.json"):
            with open("final_exploit_plan.json", "r") as f:
                data = json.load(f)
                return data
        return {"exploits": [], "total_exploits_generated": 0}
    except Exception as e:
        return {"error": str(e), "exploits": [], "total_exploits_generated": 0}

@app.get("/api/evidence")
async def get_evidence():
    """Get attack evidence (screenshots and videos)"""
    evidence = {
        "screenshots": [],
        "videos": []
    }
    
    # Get screenshots
    if os.path.exists("attack_evidence"):
        screenshots = glob.glob("attack_evidence/*.png")
        evidence["screenshots"] = [os.path.basename(s) for s in screenshots]
    
    # Get videos
    if os.path.exists("attack_videos"):
        videos = glob.glob("attack_videos/*.webm")
        evidence["videos"] = [os.path.basename(v) for v in videos]
    
    return evidence

@app.get("/api/evidence/screenshot/{filename}")
async def get_screenshot(filename: str):
    """Serve a specific screenshot"""
    path = os.path.join("attack_evidence", filename)
    if os.path.exists(path):
        return FileResponse(path)
    return {"error": "File not found"}

@app.get("/api/stats")
async def get_stats():
    """Get overall statistics"""
    stats = {
        "total_vulnerabilities": 0,
        "total_exploits": 0,
        "success_rate": 0,
        "last_run": None
    }
    
    # Count vulnerabilities
    if os.path.exists("rl_training_data.json"):
        with open("rl_training_data.json", "r") as f:
            data = json.load(f)
            stats["total_vulnerabilities"] = len([item for item in data if item.get("reward", 0) >= 0.5])
    
    # Count exploits
    if os.path.exists("final_exploit_plan.json"):
        with open("final_exploit_plan.json", "r") as f:
            data = json.load(f)
            stats["total_exploits"] = data.get("total_exploits_generated", 0)
    
    # Calculate success rate (placeholder)
    if stats["total_exploits"] > 0:
        stats["success_rate"] = 0.75  # TODO: Calculate from actual results
    
    return stats

@app.post("/api/reset")
async def reset_artifacts():
    """Clear all generated artifacts for a fresh run"""
    import shutil
    
    files_to_remove = [
        "final_exploit_plan.json",
        "rl_training_data.json",
        "qa_report.md",
        "mission_log.md",
        "agent_logs.jsonl"  # Clear the log file too
    ]
    
    dirs_to_remove = [
        "attack_evidence",
        "attack_videos",
        "qa_screenshots"
    ]
    
    removed = []
    
    # Remove files
    for file in files_to_remove:
        if os.path.exists(file):
            os.remove(file)
            removed.append(file)
    
    # Remove directories
    for dir_path in dirs_to_remove:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
            removed.append(dir_path)
    
    await manager.broadcast(json.dumps({
        "type": "log",
        "script": "system",
        "message": f"🗑️  Reset complete. Removed: {', '.join(removed)}"
    }))
    
    return {"status": "success", "removed": removed}

if __name__ == "__main__":

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
