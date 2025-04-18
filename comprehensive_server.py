"""
Comprehensive MCP Server Example

This example combines various MCP features including:
- Lifespan management
- Resources (static and dynamic)
- Tools (sync and async)
- Prompts
- Context usage
- Progress reporting
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
import json
import os
from datetime import datetime
import asyncio

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.prompts import base

# Simple in-memory database for demo purposes
class SimpleDB:
    def __init__(self):
        self.data = {
            "users": {
                "user1": {"name": "Alice", "email": "alice@example.com"},
                "user2": {"name": "Bob", "email": "bob@example.com"},
            },
            "products": {
                "prod1": {"name": "Widget", "price": 19.99},
                "prod2": {"name": "Gadget", "price": 29.99},
            }
        }
    
    async def connect(self):
        """Simulate connection process"""
        await asyncio.sleep(0.5)
        print("Database connected")
        return self
    
    async def disconnect(self):
        """Simulate disconnection process"""
        await asyncio.sleep(0.5)
        print("Database disconnected")
    
    def query(self, collection, item_id=None):
        """Query the database"""
        if item_id:
            return self.data.get(collection, {}).get(item_id, None)
        return self.data.get(collection, {})


@dataclass
class AppContext:
    """Strongly typed application context"""
    db: SimpleDB
    start_time: datetime


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with type-safe context"""
    # Initialize on startup
    print("Server starting...")
    db = SimpleDB()
    await db.connect()
    
    try:
        yield AppContext(
            db=db,
            start_time=datetime.now()
        )
    finally:
        # Cleanup on shutdown
        print("Server shutting down...")
        await db.disconnect()


# Create server with lifespan
mcp = FastMCP(
    "Comprehensive Demo",
    lifespan=app_lifespan,
)


# =========== RESOURCES ===========

@mcp.resource("config://app")
def get_config() -> str:
    """Static configuration data"""
    config = {
        "app_name": "Comprehensive MCP Demo",
        "version": "1.0.0",
        "environment": os.environ.get("APP_ENV", "development")
    }
    return json.dumps(config, indent=2)


@mcp.resource("users://{user_id}")
def get_user(user_id: str) -> str:
    """Dynamic user data from the database"""
    # Access context through the server's request_context
    db = mcp.request_context.lifespan_context.db
    user = db.query("users", user_id)
    
    if user:
        return json.dumps(user, indent=2)
    return f"User {user_id} not found"


@mcp.resource("products://all")
def get_all_products() -> str:
    """Get all products from the database"""
    # Access context through the server's request_context
    db = mcp.request_context.lifespan_context.db
    products = db.query("products")
    
    return json.dumps(products, indent=2)


# =========== TOOLS ===========

@mcp.tool()
def calculate_bmi(weight_kg: float, height_m: float) -> float:
    """Calculate BMI given weight in kg and height in meters"""
    if height_m <= 0 or weight_kg <= 0:
        raise ValueError("Height and weight must be positive values")
    
    bmi = weight_kg / (height_m**2)
    return round(bmi, 2)


@mcp.tool()
async def fetch_weather(city: str) -> str:
    """
    Fetch current weather for a city
    Note: In a real implementation, you would use a real API key
    """
    # This is a mock implementation
    weather_data = {
        "New York": {"temp": 22, "condition": "Sunny"},
        "London": {"temp": 18, "condition": "Cloudy"},
        "Tokyo": {"temp": 28, "condition": "Rainy"},
        "Sydney": {"temp": 25, "condition": "Clear"},
    }
    
    # Simulate API call delay
    await asyncio.sleep(1)
    
    if city in weather_data:
        return json.dumps(weather_data[city], indent=2)
    
    return json.dumps({"error": f"Weather data for {city} not available"})


@mcp.tool()
def server_uptime(ctx: Context) -> str:
    """Get the server's current uptime"""
    start_time = ctx.request_context.lifespan_context.start_time
    current_time = datetime.now()
    uptime = current_time - start_time
    
    return f"Server has been running for {uptime}"


@mcp.tool()
async def process_data(data_list: list[str], ctx: Context) -> str:
    """Process a list of data items with progress tracking"""
    results = []
    total_items = len(data_list)
    
    for i, item in enumerate(data_list):
        # Report progress
        ctx.info(f"Processing item {i+1}/{total_items}: {item}")
        await ctx.report_progress(i, total_items)
        
        # Simulate processing time
        await asyncio.sleep(0.5)
        
        # Process the item (reverse it for this demo)
        results.append(item[::-1])
    
    # Final progress update
    await ctx.report_progress(total_items, total_items)
    
    return json.dumps({
        "processed_items": total_items,
        "results": results
    }, indent=2)


# =========== PROMPTS ===========

@mcp.prompt()
def analyze_data(data_description: str) -> str:
    """Prompt to analyze user-provided data"""
    return f"""
    I need help analyzing the following data:
    
    {data_description}
    
    Please provide insights and suggestions based on this information.
    """


@mcp.prompt()
def debug_error(error: str) -> list[base.Message]:
    """Interactive prompt to debug an error"""
    return [
        base.UserMessage("I'm encountering this error in my application:"),
        base.UserMessage(error),
        base.AssistantMessage("I'll help debug that error. What were you trying to accomplish when this happened?"),
    ]


# Run the server if executed directly
if __name__ == "__main__":
    mcp.run()