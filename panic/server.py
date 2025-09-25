#!/usr/bin/env python3
"""
HTTP Server for Panic Button
Provides REST endpoints for panic operations.
"""

import json
import time
from dataclasses import asdict
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
import uvicorn
from typing import Dict, Any

from .config import get_config
from .service import get_panic_service
from .state import get_state_manager

app = FastAPI(
    title="Panic Button API",
    description="Emergency kill-switch for Bybit-Futures-Bot",
    version="1.0.0"
)

# Global instances
config = get_config()
panic_service = get_panic_service()
state_manager = get_state_manager()

@app.middleware("http")
async def ip_allowlist_middleware(request: Request, call_next):
    """Middleware to restrict access to allowed IPs only."""
    client_ip = request.client.host
    allowed_ips = config.http_allowlist

    if client_ip not in allowed_ips:
        return JSONResponse(
            status_code=403,
            content={"error": "Access denied", "client_ip": client_ip}
        )

    response = await call_next(request)
    return response

@app.post("/panic")
async def execute_panic():
    """
    Execute emergency panic procedure.

    Performs all 6 phases:
    1. Disable trading
    2. Cancel all orders
    3. Flatten all positions
    4. Verify clean state
    5. Create panic lock
    6. Send alerts
    """
    try:
        print(f"[API] Panic request received from client")

        # Execute panic procedure
        report = panic_service.execute_panic()

        # Convert to JSON-serializable format
        response_data = asdict(report)

        # Return appropriate status code
        status_code = 200 if report.success else 500

        return JSONResponse(
            content=response_data,
            status_code=status_code
        )

    except Exception as e:
        print(f"[API] Panic execution error: {e}")
        return JSONResponse(
            content={
                "error": "Panic execution failed",
                "message": str(e),
                "timestamp": time.time()
            },
            status_code=500
        )

@app.post("/panic/reset")
async def reset_panic():
    """
    Reset panic state and re-enable trading.

    Safety checks:
    - Verifies no positions remain
    - Verifies no orders remain
    - Only then removes lock and re-enables trading
    """
    try:
        print(f"[API] Reset request received")

        # Execute reset procedure
        result = panic_service.reset_panic()

        status_code = 200 if result.get("success", False) else 400

        return JSONResponse(
            content=result,
            status_code=status_code
        )

    except Exception as e:
        print(f"[API] Reset error: {e}")
        return JSONResponse(
            content={
                "success": False,
                "error": "Reset failed",
                "message": str(e),
                "timestamp": time.time()
            },
            status_code=500
        )

@app.get("/panic/status")
async def get_panic_status():
    """
    Get current panic system status.

    Returns:
    - Trading enabled/disabled state
    - Panic lock status
    - Last panic report summary
    - System uptime
    """
    try:
        status = state_manager.get_status()
        last_report = state_manager.get_last_report()

        response = {
            "status": status,
            "config": {
                "verify_timeout_sec": config.verify_timeout,
                "max_retries": config.max_retries,
                "symbols_scope": config.symbols_scope
            }
        }

        if last_report:
            response["last_report_summary"] = {
                "timestamp": last_report.started_at,
                "success": last_report.success,
                "duration_sec": last_report.total_duration_sec,
                "orders_canceled": last_report.orders_canceled,
                "positions_closed": last_report.positions_closed,
                "symbols_count": len(last_report.symbols_touched),
                "warnings_count": len(last_report.warnings)
            }

        return JSONResponse(content=response)

    except Exception as e:
        print(f"[API] Status error: {e}")
        return JSONResponse(
            content={
                "error": "Status retrieval failed",
                "message": str(e)
            },
            status_code=500
        )

@app.get("/healthz")
async def health_check():
    """
    Health check endpoint.

    Returns:
    - Service health
    - Trading state
    - Panic state
    - Configuration status
    """
    try:
        health_data = {
            "status": "healthy",
            "timestamp": time.time(),
            "trading_enabled": state_manager.is_trading_enabled(),
            "panic_tripped": state_manager.is_panic_active(),
            "config_loaded": True,
            "client_available": panic_service.client is not None,
            "uptime_sec": time.time() - int(time.time()) # Simplified uptime
        }

        return JSONResponse(content=health_data)

    except Exception as e:
        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            },
            status_code=503
        )

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Panic Button API",
        "version": "1.0.0",
        "description": "Emergency kill-switch for Bybit-Futures-Bot",
        "endpoints": {
            "POST /panic": "Execute emergency panic procedure",
            "POST /panic/reset": "Reset panic state",
            "GET /panic/status": "Get panic system status",
            "GET /healthz": "Health check"
        },
        "status": "operational" if state_manager.is_trading_enabled() else "locked"
    }

def start_server():
    """Start the panic button HTTP server."""
    print(f"[SERVER] Starting panic button server on {config.http_host}:{config.http_port}")
    print(f"[SERVER] Allowed IPs: {config.http_allowlist}")
    print(f"[SERVER] Trading enabled: {state_manager.is_trading_enabled()}")
    print(f"[SERVER] Panic active: {state_manager.is_panic_active()}")

    uvicorn.run(
        app,
        host=config.http_host,
        port=config.http_port,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    start_server()