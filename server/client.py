import asyncio
import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

from mcp_use import MCPAgent, MCPClient

async def run_memory_chat():
    """Run a chat using MCPAgent's built-in conversation memory."""
    # Load environment variables for API keys
    load_dotenv()
    
    # Set environment variables
    os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY")
    os.environ["QLOO_API_KEY"] = os.getenv("QLOO_API_KEY")
    
    # Check if API keys are loaded
    if not os.getenv("QLOO_API_KEY"):
        print("Warning: QLOO_API_KEY not found in environment variables")
        print("Please make sure your .env file contains: QLOO_API_KEY=your_api_key_here")
        return
    
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Warning: ANTHROPIC_API_KEY not found in environment variables")
        print("Please make sure your .env file contains: ANTHROPIC_API_KEY=your_api_key_here")
        return

    # Config file path - using the existing qloo.json
    config_file = "server/qloo.json"

    print("Initializing CultureShift AI with Claude...")

    # Create MCP client and agent with memory enabled
    client = MCPClient.from_config_file(config_file)
    llm = ChatAnthropic(
        model="claude-3-5-sonnet-20241022",  # Latest Claude model
        temperature=0.1,  # Lower temperature for more consistent analysis
        max_tokens=4000
    )

    # Create agent with memory_enabled=True
    agent = MCPAgent(
        llm=llm,
        client=client,
        max_steps=15,
        memory_enabled=True,  # Enable built-in conversation memory
    )

    print("\n===== CultureShift AI: Real Estate Investment Intelligence =====")
    print("Type 'exit' or 'quit' to end the conversation")
    print("Type 'clear' to clear conversation history")
    print("\n🎯 **Available Cultural Intelligence Commands:**")
    print("- Analyze cultural hotspots: 'Find cultural hotspots in Brooklyn for vegan food, yoga studios'")
    print("- Demographic analysis: 'What demographics like craft beer, indie music venues?'")
    print("- Neighborhood profiling: 'Analyze cultural DNA of Williamsburg for restaurants, bars'")
    print("- Tag discovery: 'Discover available tags for korean food'")
    print("==================================================================\n")

    try:
        # Main chat loop
        while True:
            # Get user input
            user_input = input("\nYou: ")

            # Check for exit command
            if user_input.lower() in ["exit", "quit"]:
                print("Ending CultureShift AI session...")
                break

            # Check for clear history command
            if user_input.lower() == "clear":
                agent.clear_conversation_history()
                print("Conversation history cleared.")
                continue

            # Get response from agent
            print("\nCultureShift AI: ", end="", flush=True)

            try:
                # Run the agent with the user input (memory handling is automatic)
                response = await agent.run(user_input)
                print(response)

            except Exception as e:
                print(f"\nError: {e}")

    finally:
        # Clean up
        if client and client.sessions:
            await client.close_all_sessions()


if __name__ == "__main__":
    asyncio.run(run_memory_chat())