import asyncio
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

from mcp_use import MCPAgent, MCPClient

async def run_memory_chat():
    """Run a chat using MCPAgent's built-in conversation memory."""
    # Load environment variables for API keys
    load_dotenv()
    
    # Set environment variables
    os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
    os.environ["QLOO_API_KEY"] = os.getenv("QLOO_API_KEY")  # Add this line
    
    # Check if API keys are loaded
    if not os.getenv("QLOO_API_KEY"):
        print("Warning: QLOO_API_KEY not found in environment variables")
        print("Please make sure your .env file contains: QLOO_API_KEY=your_api_key_here")
        return
    
    if not os.getenv("GROQ_API_KEY"):
        print("Warning: GROQ_API_KEY not found in environment variables")
        return

    # Config file path - updated to use qloo.json
    config_file = "server/qloo.json"

    print("Initializing chat...")

    # Create MCP client and agent with memory enabled
    client = MCPClient.from_config_file(config_file)
    llm = ChatGroq(model="llama-3.3-70b-versatile")

    # Create agent with memory_enabled=True
    agent = MCPAgent(
        llm=llm,
        client=client,
        max_steps=15,
        memory_enabled=True,  # Enable built-in conversation memory
    )

    print("\n===== Interactive MCP Chat =====")
    print("Type 'exit' or 'quit' to end the conversation")
    print("Type 'clear' to clear conversation history")
    print("Available commands:")
    print("- Ask for restaurant recommendations: 'Find Japanese restaurants in Mumbai'")
    print("- Ask for general places: 'Find cafes in Tokyo'")
    print("- Get weather alerts: 'Get alerts for CA'")
    print("==================================\n")

    try:
        # Main chat loop
        while True:
            # Get user input
            user_input = input("\nYou: ")

            # Check for exit command
            if user_input.lower() in ["exit", "quit"]:
                print("Ending conversation...")
                break

            # Check for clear history command
            if user_input.lower() == "clear":
                agent.clear_conversation_history()
                print("Conversation history cleared.")
                continue

            # Get response from agent
            print("\nAssistant: ", end="", flush=True)

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