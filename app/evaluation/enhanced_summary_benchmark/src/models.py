import abc
import os
import time
import asyncio
from typing import List, Optional
import openai
import google.generativeai as genai
from src.types import LLMResponse, TokenUsage

class LLMClient(abc.ABC):
    def __init__(self, model_name: str):
        self.model_name = model_name

    @abc.abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        assistant_prompt: Optional[str] = None,
    ) -> LLMResponse:
        pass

class OpenAIClient(LLMClient):
    def __init__(self, model_name: str):
        super().__init__(model_name)
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        assistant_prompt: Optional[str] = None,
    ) -> LLMResponse:
        start = time.perf_counter()
        
        kwargs = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                *([{"role": "assistant", "content": assistant_prompt}] if assistant_prompt else []),
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        duration = time.perf_counter() - start
        
        u = response.usage
        usage = TokenUsage(u.prompt_tokens, u.completion_tokens, u.total_tokens)
        
        return LLMResponse(
            content=response.choices[0].message.content,
            usage=usage,
            latency=duration
        )

class GeminiClient(LLMClient):
    def __init__(self, model_name: str):
        super().__init__(model_name)
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model = genai.GenerativeModel(model_name)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        assistant_prompt: Optional[str] = None,
    ) -> LLMResponse:
        start = time.perf_counter()
        
        # Gemini handles system prompts differently, simplifying here by prepending
        full_prompt = f"SYSTEM: {system_prompt}\n"
        if assistant_prompt:
            full_prompt += f"ASSISTANT (príklady): {assistant_prompt}\n"
        full_prompt += f"USER: {user_prompt}"
        if json_mode:
            full_prompt += "\nReturn valid JSON."

        # Run sync Gemini call in thread pool to be async compliant
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: self.model.generate_content(full_prompt))
        
        duration = time.perf_counter() - start
        
        # Estimate tokens if usage_metadata is missing (Gemini behavior varies by version)
        # Note: In prod, use strict count. Here we use simple fallback.
        if hasattr(response, 'usage_metadata'):
            usage = TokenUsage(
                response.usage_metadata.prompt_token_count,
                response.usage_metadata.candidates_token_count,
                response.usage_metadata.total_token_count
            )
        else:
            # Fallback estimation
            in_len = len(full_prompt) // 4
            out_len = len(response.text) // 4
            usage = TokenUsage(in_len, out_len, in_len + out_len)

        return LLMResponse(content=response.text, usage=usage, latency=duration)

def get_client(model_name: str) -> LLMClient:
    if "gpt" in model_name.lower():
        return OpenAIClient(model_name)
    elif "gemini" in model_name.lower():
        return GeminiClient(model_name)
    else:
        raise ValueError(f"Unsupported model provider for {model_name}")
