"""Example: Using LLMClient with different providers.

This example demonstrates how to use the LLMClient wrapper with different
LLM providers (Anthropic or OpenAI) through the provider parameter.
"""

import asyncio

from box_agent import LLMClient, LLMProvider, Message
from box_agent.config import Config


def load_config() -> Config:
    """Load the same config file used by the CLI."""
    config_path = Config.find_config_file("config.yaml")
    if not config_path:
        raise FileNotFoundError("config.yaml not found. Run: box-agent setup")
    return Config.from_yaml(config_path)


def provider_from_config(config: Config) -> LLMProvider:
    """Return the configured provider enum."""
    return LLMProvider.ANTHROPIC if config.llm.provider.lower() == "anthropic" else LLMProvider.OPENAI


async def demo_anthropic_provider():
    """Demo using LLMClient with Anthropic provider."""
    print("\n" + "=" * 60)
    print("DEMO: LLMClient with Anthropic Provider")
    print("=" * 60)

    config = load_config()

    # Initialize client with Anthropic provider
    client = LLMClient(
        api_key=config.llm.api_key,
        provider=LLMProvider.ANTHROPIC,  # Specify Anthropic provider
        api_base=config.llm.api_base,
        model=config.llm.model or "claude-sonnet-4-20250514",
    )

    print(f"Provider: {client.provider}")
    print(f"API Base: {client.api_base}")

    # Simple question
    messages = [Message(role="user", content="Say 'Hello from Anthropic!'")]
    print(f"\n👤 User: {messages[0].content}")

    try:
        response = await client.generate(messages)
        if response.thinking:
            print(f"💭 Thinking: {response.thinking}")
        print(f"💬 Model: {response.content}")
        print("✅ Anthropic provider demo completed")
    except Exception as e:
        print(f"❌ Error: {e}")


async def demo_openai_provider():
    """Demo using LLMClient with OpenAI provider."""
    print("\n" + "=" * 60)
    print("DEMO: LLMClient with OpenAI Provider")
    print("=" * 60)

    config = load_config()

    # Initialize client with OpenAI provider
    client = LLMClient(
        api_key=config.llm.api_key,
        provider=LLMProvider.OPENAI,  # Specify OpenAI provider
        api_base=config.llm.api_base,
        model=config.llm.model or "gpt-4o",
    )

    print(f"Provider: {client.provider}")
    print(f"API Base: {client.api_base}")

    # Simple question
    messages = [Message(role="user", content="Say 'Hello from OpenAI!'")]
    print(f"\n👤 User: {messages[0].content}")

    try:
        response = await client.generate(messages)
        if response.thinking:
            print(f"💭 Thinking: {response.thinking}")
        print(f"💬 Model: {response.content}")
        print("✅ OpenAI provider demo completed")
    except Exception as e:
        print(f"❌ Error: {e}")


async def demo_configured_provider():
    """Demo using LLMClient with the configured provider."""
    print("\n" + "=" * 60)
    print("DEMO: LLMClient with Configured Provider")
    print("=" * 60)

    config = load_config()

    client = LLMClient(
        api_key=config.llm.api_key,
        provider=provider_from_config(config),
        api_base=config.llm.api_base,
        model=config.llm.model or "claude-sonnet-4-20250514",
    )

    print(f"Provider (configured): {client.provider}")
    print(f"API Base: {client.api_base}")

    # Simple question
    messages = [Message(role="user", content="Say 'Hello with default provider!'")]
    print(f"\n👤 User: {messages[0].content}")

    try:
        response = await client.generate(messages)
        print(f"💬 Model: {response.content}")
        print("✅ Configured provider demo completed")
    except Exception as e:
        print(f"❌ Error: {e}")


async def demo_provider_comparison():
    """Compare responses from both providers."""
    print("\n" + "=" * 60)
    print("DEMO: Provider Comparison")
    print("=" * 60)

    config = load_config()

    # Create clients for both providers
    anthropic_client = LLMClient(
        api_key=config.llm.api_key,
        provider=LLMProvider.ANTHROPIC,
        api_base=config.llm.api_base,
        model=config.llm.model or "claude-sonnet-4-20250514",
    )

    openai_client = LLMClient(
        api_key=config.llm.api_key,
        provider=LLMProvider.OPENAI,
        api_base=config.llm.api_base,
        model=config.llm.model or "gpt-4o",
    )

    # Same question for both
    messages = [Message(role="user", content="What is 2+2?")]
    print(f"\n👤 Question: {messages[0].content}\n")

    try:
        # Get response from Anthropic
        anthropic_response = await anthropic_client.generate(messages)
        print(f"🔵 Anthropic: {anthropic_response.content}")

        # Get response from OpenAI
        openai_response = await openai_client.generate(messages)
        print(f"🟢 OpenAI: {openai_response.content}")

        print("\n✅ Provider comparison completed")
    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Run all demos."""
    print("\n🚀 LLM Provider Selection Demo")
    print("This demo shows how to use LLMClient with different providers.")
    print("Make sure you have configured API key in config.yaml.")

    try:
        # Demo configured provider
        await demo_configured_provider()

        # Demo Anthropic provider
        await demo_anthropic_provider()

        # Demo OpenAI provider
        await demo_openai_provider()

        # Demo provider comparison
        await demo_provider_comparison()

        print("\n✅ All demos completed successfully!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
