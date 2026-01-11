#!/usr/bin/env python3
"""Standalone web server for testing"""
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot.server:instance", host="0.0.0.0", port=5000, reload=False)
