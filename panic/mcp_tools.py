#!/usr/bin/env python3
"""
MCP Tools Integration for Panic Button
Provides Claude-accessible tools for panic operations.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import asdict

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from .service import get_panic_service
from .state import get_state_manager
from .config import get_config

class PanicMCPTools:
    """MCP tools for panic button operations."""

    def __init__(self):
        self.panic_service = get_panic_service()
        self.state_manager = get_state_manager()
        self.config = get_config()

    def panic_stop(self) -> Dict[str, Any]:
        """
        MCP Tool: Execute emergency panic procedure.

        Triggers the full 6-phase panic procedure:
        1. Disable trading
        2. Cancel all orders
        3. Flatten all positions
        4. Verify clean state
        5. Create panic lock
        6. Send alerts

        Returns detailed execution report.
        """
        try:
            print("[MCP-TOOL] panic_stop: Executing emergency panic procedure...")

            # Execute panic
            report = self.panic_service.execute_panic()

            # Convert to JSON-serializable format
            result = asdict(report)

            # Add summary for Claude
            result["summary"] = {
                "success": report.success,
                "total_duration": f"{report.total_duration_sec:.2f} seconds",
                "orders_canceled": report.orders_canceled,
                "positions_closed": report.positions_closed,
                "symbols_affected": len(report.symbols_touched),
                "warnings_count": len(report.warnings),
                "status": "LOCKED" if report.locked else "UNLOCKED"
            }

            if report.success:
                result["message"] = "✅ Panic procedure completed successfully. All positions closed and orders canceled."
            else:
                result["message"] = "❌ Panic procedure completed with errors. Manual verification required."

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"❌ Panic execution failed: {str(e)}",
                "summary": {
                    "success": False,
                    "error": str(e)
                }
            }

    def panic_status(self) -> Dict[str, Any]:
        """
        MCP Tool: Get current panic system status.

        Returns:
        - Current trading state
        - Panic lock status
        - Last execution summary
        - System configuration
        """
        try:
            status = self.state_manager.get_status()
            last_report = self.state_manager.get_last_report()

            result = {
                "current_status": {
                    "trading_enabled": status["trading_enabled"],
                    "panic_active": status["panic_tripped"],
                    "lock_file_exists": status["lock_file_exists"]
                },
                "system_info": {
                    "verify_timeout_sec": self.config.verify_timeout,
                    "max_retries": self.config.max_retries,
                    "symbols_scope": self.config.symbols_scope,
                    "server_port": self.config.http_port
                }
            }

            if last_report:
                result["last_execution"] = {
                    "timestamp": last_report.started_at,
                    "success": last_report.success,
                    "duration_sec": last_report.total_duration_sec,
                    "orders_canceled": last_report.orders_canceled,
                    "positions_closed": last_report.positions_closed,
                    "symbols_touched": last_report.symbols_touched,
                    "warnings": last_report.warnings[:3] if last_report.warnings else [],  # First 3 warnings
                    "warnings_total": len(last_report.warnings)
                }

                if last_report.phase_timings:
                    result["last_execution"]["phase_timings"] = last_report.phase_timings

            # Add human-readable summary
            if status["panic_tripped"]:
                result["summary"] = "🔒 System is LOCKED - Panic mode active. Use panic_reset to unlock after verification."
            elif status["trading_enabled"]:
                result["summary"] = "✅ System operational - Trading enabled, no panic active."
            else:
                result["summary"] = "⚠️ Trading disabled but no panic lock detected."

            return result

        except Exception as e:
            return {
                "error": str(e),
                "summary": f"❌ Status check failed: {str(e)}"
            }

    def panic_reset(self) -> Dict[str, Any]:
        """
        MCP Tool: Reset panic state after verification.

        Safety checks:
        - Verifies no positions remain open
        - Verifies no orders remain active
        - Only then removes panic lock
        - Re-enables trading

        Returns reset operation result.
        """
        try:
            print("[MCP-TOOL] panic_reset: Attempting to reset panic state...")

            # Execute reset
            result = self.panic_service.reset_panic()

            # Add summary for Claude
            if result.get("success", False):
                result["summary"] = "✅ Panic reset successful. Trading is now enabled."
                result["message"] = "System unlocked and ready for normal operations."
            else:
                error = result.get("error", "Unknown error")
                result["summary"] = f"❌ Reset failed: {error}"
                result["message"] = "Manual intervention required. Check positions and orders manually."

                # Add specific safety information if available
                if "positions_remaining" in result or "orders_remaining" in result:
                    positions = result.get("positions_remaining", 0)
                    orders = result.get("orders_remaining", 0)
                    result["safety_check"] = {
                        "positions_remaining": positions,
                        "orders_remaining": orders,
                        "reason": "Cannot reset while positions or orders remain open"
                    }

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "summary": f"❌ Reset operation failed: {str(e)}",
                "message": "Exception occurred during reset. Check system manually."
            }

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available MCP tools with descriptions."""
        return [
            {
                "name": "panic_stop",
                "description": "Execute emergency panic procedure - closes all positions and cancels all orders",
                "parameters": {},
                "returns": "Detailed execution report with timings and results"
            },
            {
                "name": "panic_status",
                "description": "Get current panic system status and last execution summary",
                "parameters": {},
                "returns": "Current system state, trading status, and execution history"
            },
            {
                "name": "panic_reset",
                "description": "Reset panic state and re-enable trading (with safety checks)",
                "parameters": {},
                "returns": "Reset operation result with safety verification"
            }
        ]

# Global MCP tools instance
_mcp_tools = None

def get_mcp_tools() -> PanicMCPTools:
    """Get global MCP tools instance."""
    global _mcp_tools
    if _mcp_tools is None:
        _mcp_tools = PanicMCPTools()
    return _mcp_tools

# MCP Server Implementation (if running as standalone server)
def run_mcp_server():
    """Run as MCP server for external tool access."""
    import asyncio
    from mcp import McpServer
    from mcp.types import Tool, TextContent

    tools = get_mcp_tools()
    server = McpServer("panic-button")

    @server.list_tools()
    async def list_tools():
        """List available panic button tools."""
        return [
            Tool(
                name="panic_stop",
                description="Execute emergency panic procedure - closes all positions and cancels all orders",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="panic_status",
                description="Get current panic system status and last execution summary",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="panic_reset",
                description="Reset panic state and re-enable trading (with safety checks)",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Execute panic button tools."""
        try:
            if name == "panic_stop":
                result = tools.panic_stop()
            elif name == "panic_status":
                result = tools.panic_status()
            elif name == "panic_reset":
                result = tools.panic_reset()
            else:
                raise ValueError(f"Unknown tool: {name}")

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]

        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Tool execution error: {str(e)}"
            )]

    return server

if __name__ == "__main__":
    # Test the MCP tools directly
    tools = get_mcp_tools()

    print("Available MCP Tools:")
    for tool in tools.get_available_tools():
        print(f"- {tool['name']}: {tool['description']}")

    print("\nTesting panic_status:")
    status = tools.panic_status()
    print(json.dumps(status, indent=2, default=str))