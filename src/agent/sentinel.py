"""
Sentinel Agent - Gemini-powered autonomous astronomical transient detector.

This module implements the core AI agent that:
- Analyzes telescope images using Gemini 3 Flash Preview
- Tracks transient candidates across iterations
- Makes autonomous decisions in the OODA loop
- Handles errors and API failures gracefully
"""

import os
import io
import re
import json
import time
import base64
import logging
from typing import List, Optional, Tuple, Union
from pathlib import Path

import numpy as np
from PIL import Image
from dotenv import load_dotenv
from pydantic import ValidationError

# Google Gemini API
from google import genai
from google.genai import types

from .models import (
    ContextState,
    AgentDecision,
    Candidate,
    WeatherContext,
    create_default_wait_decision
)
from .prompts import build_full_prompt, SYSTEM_INSTRUCTION, OBSERVATION_SESSION_INSTRUCTION

# Configure logging
logger = logging.getLogger(__name__)


class SentinelAgent:
    """
    Gemini-powered autonomous astronomical agent.
    
    This agent implements the DECIDE phase of the OODA loop:
    - Receives telescope images and context state
    - Analyzes images using Gemini vision capabilities
    - Outputs structured decisions for transient detection
    - Uses persistent chat sessions for long-context reasoning
    
    Attributes:
        client: Gemini API client
        model_name: Name of the Gemini model to use
        temperature: Sampling temperature (lower = more deterministic)
        max_retries: Maximum retry attempts on failure
        retry_delay: Base delay between retries in seconds
        api_keys: List of API keys for rotation
        current_key_index: Index of currently active API key
        chat_session: Persistent chat session for long-context observation
        conversation_history: History of all messages for debugging
        session_active: Whether a chat session is currently active
    """
    
    DEFAULT_MODEL = "gemini-3.0-flash"
    MAX_IMAGE_SIZE = 4096  # Gemini max dimension
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_keys: Optional[List[str]] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.2,
        max_retries: int = 3,
        retry_delay: float = 2.0
    ):
        """
        Initialize the Sentinel Agent.
        
        Args:
            api_key: Single Google API key. If None, loads from env.
            api_keys: List of API keys for rotation. Takes precedence over api_key.
            model_name: Gemini model name. Defaults to gemini-3.0-flash.
            temperature: Sampling temperature (0.0-1.0). Lower = more consistent.
            max_retries: Maximum API retry attempts.
            retry_delay: Base delay between retries in seconds.
        """
        # Load environment variables
        load_dotenv()
        
        # Load API keys (support both single key and multiple keys)
        self.api_keys = self._load_api_keys(api_key, api_keys)
        if not self.api_keys:
            raise ValueError(
                "No API keys found. Set GOOGLE_API_KEYS in .env file or pass api_key/api_keys parameter."
            )
        
        self.current_key_index = 0
        logger.info(f"Loaded {len(self.api_keys)} API key(s) for rotation")
        
        # Initialize Gemini client with first key
        self.client = genai.Client(api_key=self.api_keys[0])
        
        # Model configuration
        self.model_name = model_name or os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL)
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Persistent chat session for long-context reasoning
        self.chat_session = None
        self.conversation_history = []
        self.session_active = False
        
        # Image labels for chat messages
        self._image_labels = [
            "REFERENCE IMAGE (clean sky from 1 year ago):",
            "CURRENT OBSERVATION (latest telescope image):",
            "DIFFERENCE IMAGE (annotated with candidate regions):"
        ]
        
        logger.info(f"SentinelAgent initialized with model: {self.model_name}")
    
    def _load_api_keys(
        self,
        api_key: Optional[str],
        api_keys: Optional[List[str]]
    ) -> List[str]:
        """
        Load API keys from parameters or environment.
        
        Priority:
        1. api_keys parameter (list)
        2. api_key parameter (single)
        3. GOOGLE_API_KEYS env var (comma-separated)
        4. GOOGLE_API_KEY env var (single, legacy)
        
        Returns:
            List of API keys (may be empty)
        """
        # Priority 1: explicit list
        if api_keys:
            return [k.strip() for k in api_keys if k.strip()]
        
        # Priority 2: single key parameter
        if api_key:
            return [api_key.strip()]
        
        # Priority 3: comma-separated env var
        keys_env = os.getenv("GOOGLE_API_KEYS", "")
        if keys_env:
            keys = [k.strip() for k in keys_env.split(",") if k.strip()]
            if keys:
                return keys
        
        # Priority 4: legacy single key env var
        single_key = os.getenv("GOOGLE_API_KEY", "")
        if single_key:
            return [single_key.strip()]
        
        return []
    
    def _rotate_api_key(self) -> bool:
        """
        Rotate to the next API key in the list.
        
        Returns:
            True if rotated to a new key, False if only one key available
        """
        if len(self.api_keys) <= 1:
            return False
        
        old_index = self.current_key_index
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        
        # Reinitialize client with new key
        self.client = genai.Client(api_key=self.api_keys[self.current_key_index])
        
        logger.info(f"Rotated API key: {old_index + 1} → {self.current_key_index + 1} of {len(self.api_keys)}")
        return True
    
    def analyze_images(
        self,
        reference: np.ndarray,
        current: np.ndarray,
        diff_annotated: np.ndarray,
        context: ContextState
    ) -> AgentDecision:
        """
        Analyze telescope images and make a decision using persistent chat session.
        
        This is the main entry point for the agent. It:
        1. Starts a chat session if not already active
        2. Prepares images for the API
        3. Sends observation to the chat session
        4. Parses and validates the response
        
        Args:
            reference: Reference image (clean sky) as numpy array
            current: Current observation as numpy array
            diff_annotated: Difference image with annotations as numpy array
            context: Current agent state with candidates and history
        
        Returns:
            AgentDecision with action, reasoning, and updated candidates
        """
        logger.info(f"Analyzing images for iteration {context.iteration}")
        
        # Check weather - short-circuit if unusable
        if context.weather.observability == "UNUSABLE":
            logger.warning("Weather UNUSABLE - returning wait decision")
            return create_default_wait_decision(
                f"Weather conditions UNUSABLE (clouds: {context.weather.cloud_extinction:.1%}). "
                "Waiting for conditions to improve."
            )
        
        # Ensure chat session is started
        if not self.chat_session:
            self.start_observation_session(context)
        
        # Prepare images
        try:
            images = self._prepare_images(reference, current, diff_annotated)
        except Exception as e:
            logger.error(f"Image preparation failed: {e}")
            return create_default_wait_decision(f"Image preparation error: {e}")
        
        # Send observation to chat session
        decision = self._send_observation(images, context)
        
        logger.info(f"Decision: {decision.action} (confidence: {decision.confidence:.2f})")
        return decision
    
    def start_observation_session(self, initial_context: ContextState) -> None:
        """
        Initialize persistent chat session for long-context observation.
        
        This creates a Gemini chat session that maintains conversation history
        across multiple observations, enabling the agent to:
        - Reference past observations
        - Track long-term trends
        - Build confidence over time
        
        Args:
            initial_context: Initial context state for the session
        """
        if self.session_active:
            logger.warning("Session already active, ending previous session")
            self.end_observation_session()
        
        logger.info("Starting observation session...")
        
        # Format the system instruction with initial context
        system_prompt = OBSERVATION_SESSION_INSTRUCTION.format(
            simulated_time=initial_context.simulated_time,
            num_candidates=len(initial_context.candidates)
        )
        
        try:
            from google.genai import types
            
            self.chat_session = self.client.chats.create(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
                    response_mime_type="application/json",
                    system_instruction=system_prompt,
                    # Enable thinking mode for visible reasoning process
                    thinking_config=types.ThinkingConfig(thinking_level="high"),
                    max_output_tokens=16384  # Increased for detailed responses
                )
            )
            self.session_active = True
            self.conversation_history = []
            logger.info("✓ Observation session started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start observation session: {e}")
            raise
    
    def _send_observation(
        self,
        images: List[Image.Image],
        context: ContextState
    ) -> AgentDecision:
        """
        Send observation to the active chat session.
        
        This method builds a concise message (since full context is in chat memory)
        and sends it along with the three telescope images.
        
        Args:
            images: List of [reference, current, difference] PIL images
            context: Current context with weather and candidates
            
        Returns:
            Parsed AgentDecision from the model response
        """
        from .prompts import build_context_prompt
        
        # Build observation message
        observation_prompt = build_context_prompt(context)
        
        # Build content list with labeled images
        contents = []
        for label, img in zip(self._image_labels, images):
            contents.append(label)
            contents.append(img)
        contents.append(observation_prompt)
        
        # Send to chat session with retry logic
        response_text = None
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Guard against None session
                if not self.chat_session:
                    raise RuntimeError("Chat session not active - call start_observation_session first")
                
                response = self.chat_session.send_message(contents)
                response_text = response.text
                
                # Extract and log thinking tokens for visibility
                self._log_thinking_process(response)
                break
            except Exception as e:
                last_error = e
                logger.warning(f"Chat send attempt {attempt + 1} failed: {e}")
                
                # Try rotating API key if rate limited
                if "429" in str(e) or "quota" in str(e).lower():
                    if self._rotate_api_key():
                        # Preserve history and replay context to new session
                        preserved_history = self.conversation_history.copy()
                        self.end_observation_session()
                        self.start_observation_session(context)
                        self.conversation_history = preserved_history
                        
                        # Replay context summary to new session for continuity
                        if preserved_history:
                            self._replay_context_to_session(preserved_history)
                            logger.info(f"Replayed {len(preserved_history)} observations to new session after key rotation")
                
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
        
        if response_text is None:
            logger.error(f"All chat attempts failed: {last_error}")
            return create_default_wait_decision(f"API error after {self.max_retries} attempts: {last_error}")
        
        # Track conversation for debugging
        self.conversation_history.append({
            "iteration": context.iteration,
            "simulated_time": context.simulated_time,
            "response": response_text[:500]  # Truncate for memory
        })
        
        # Parse response
        return self._parse_response(response_text, context)
    
    def _log_thinking_process(self, response) -> None:
        """
        Extract and log the thinking tokens from Gemini response.
        
        This makes the model's reasoning process visible in OODA logs,
        which is valuable for judges to see how the agent analyzes observations.
        
        Args:
            response: The Gemini API response object
        """
        try:
            # Check if response has candidates with thinking content
            if not hasattr(response, 'candidates') or not response.candidates:
                return
            
            for candidate in response.candidates:
                if not hasattr(candidate, 'content') or not candidate.content:
                    continue
                    
                for part in candidate.content.parts:
                    # Check for thinking part (thought=True indicates thinking content)
                    if hasattr(part, 'thought') and part.thought:
                        thinking_text = getattr(part, 'text', '')
                        if thinking_text:
                            logger.info("🧠 AGENT THINKING PROCESS:")
                            # Log each line of thinking for visibility
                            for line in thinking_text.split('\n')[:20]:  # Limit to first 20 lines
                                if line.strip():
                                    logger.info(f"   💭 {line.strip()}")
                            if thinking_text.count('\n') > 20:
                                logger.info(f"   ... ({thinking_text.count(chr(10)) - 20} more lines)")
                            return
        except Exception as e:
            logger.debug(f"Could not extract thinking tokens: {e}")
    
    def _replay_context_to_session(self, history: List[dict]) -> None:
        """
        Replay a summary of past observations to a new chat session.
        
        This is called after API key rotation to restore conversation context.
        Instead of replaying raw images (expensive), we inject a text summary
        that provides the agent with continuity about what was observed.
        
        Args:
            history: List of past conversation history entries
        """
        if not self.chat_session or not history:
            return
        
        # Build a concise summary of past observations
        summary_lines = [
            "CONTEXT RESTORATION: The following summarizes observations from the current session",
            "that were made before an API connection reset. Use this to maintain continuity.",
            ""
        ]
        
        for entry in history:
            iteration = entry.get("iteration", "?")
            sim_time = entry.get("simulated_time", "unknown")
            response_snippet = entry.get("response", "")[:200]
            summary_lines.append(f"Iteration {iteration} ({sim_time}): {response_snippet}...")
        
        context_message = "\n".join(summary_lines)
        
        try:
            # Send context summary to new session (no images, just text)
            self.chat_session.send_message(context_message)
            logger.debug(f"Context replay successful: {len(history)} entries summarized")
        except Exception as e:
            logger.warning(f"Context replay failed (non-critical): {e}")
    
    def end_observation_session(self) -> List[dict]:
        """
        End the current observation session.
        
        Returns:
            List of conversation history entries for analysis
        """
        if self.chat_session:
            logger.info(f"Ending observation session ({len(self.conversation_history)} observations)")
            self.chat_session = None
        
        self.session_active = False
        history = self.conversation_history
        self.conversation_history = []
        return history
    
    def _prepare_images(
        self,
        reference: np.ndarray,
        current: np.ndarray,
        diff_annotated: np.ndarray
    ) -> List[Image.Image]:
        """
        Convert numpy arrays to PIL Images for the API.
        
        Args:
            reference: Reference image array
            current: Current observation array
            diff_annotated: Annotated difference image array
        
        Returns:
            List of three PIL Images
        """
        images = []
        
        for idx, (arr, name) in enumerate([
            (reference, "Reference"),
            (current, "Current"),
            (diff_annotated, "Difference")
        ]):
            # Normalize to 0-255 range
            if arr.dtype != np.uint8:
                # Handle both float and high-bit images
                if arr.max() > 0:
                    # Log scaling for astronomical images
                    arr_norm = arr.astype(np.float64)
                    arr_norm = np.clip(arr_norm, 1, None)  # Avoid log(0)
                    arr_norm = np.log10(arr_norm)
                    arr_norm = (arr_norm - arr_norm.min()) / (arr_norm.max() - arr_norm.min() + 1e-10)
                    arr_norm = (arr_norm * 255).astype(np.uint8)
                else:
                    arr_norm = np.zeros_like(arr, dtype=np.uint8)
            else:
                arr_norm = arr
            
            # Convert to PIL Image
            if arr_norm.ndim == 2:
                # Grayscale
                img = Image.fromarray(arr_norm, mode='L')
                # Convert to RGB for Gemini
                img = img.convert('RGB')
            elif arr_norm.ndim == 3:
                if arr_norm.shape[2] == 3:
                    img = Image.fromarray(arr_norm, mode='RGB')
                elif arr_norm.shape[2] == 4:
                    img = Image.fromarray(arr_norm, mode='RGBA')
                    img = img.convert('RGB')
                else:
                    raise ValueError(f"Unexpected image shape: {arr_norm.shape}")
            else:
                raise ValueError(f"Unexpected image dimensions: {arr_norm.ndim}")
            
            # Resize if needed
            if max(img.size) > self.MAX_IMAGE_SIZE:
                ratio = self.MAX_IMAGE_SIZE / max(img.size)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.debug(f"Resized {name} image to {new_size}")
            
            images.append(img)
        
        return images
    
    def _call_gemini_with_retry(
        self,
        prompt: str,
        images: List[Image.Image]
    ) -> str:
        """
        Call Gemini API with retry logic.
        
        Args:
            prompt: The text prompt to send
            images: List of PIL Images to analyze
        
        Returns:
            Response text from Gemini
        """
        current_temp = self.temperature
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"API call attempt {attempt + 1}/{self.max_retries}")
                
                # Build content parts with labeled images
                contents = []
                
                # Add images with labels
                image_labels = ["REFERENCE IMAGE (clean sky from 1 year ago):",
                               "CURRENT OBSERVATION (latest telescope image):",
                               "DIFFERENCE IMAGE (annotated with candidate regions):"]
                
                for label, img in zip(image_labels, images):
                    contents.append(label)
                    contents.append(img)
                
                # Add the prompt
                contents.append("\n" + prompt)
                
                # Configure generation with JSON output mode
                config = types.GenerateContentConfig(
                    temperature=current_temp,
                    max_output_tokens=8192,  # Increased from 4096 to prevent response truncation
                    candidate_count=1,
                    response_mime_type="application/json",  # Force valid JSON output
                )
                
                # Make API call
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config
                )
                
                # Extract text and log raw response
                if response.text:
                    raw_text = response.text
                    # Log the raw response for debugging
                    logger.info(f"=== RAW GEMINI RESPONSE (length: {len(raw_text)}) ===")
                    logger.info(f"First 500 chars: {raw_text[:500]}")
                    logger.info(f"Last 200 chars: {raw_text[-200:] if len(raw_text) > 200 else raw_text}")
                    logger.info("=== END RAW RESPONSE ===")
                    return raw_text
                else:
                    logger.warning("Empty response from Gemini")
                    raise ValueError("Empty response received")
                
            except Exception as e:
                error_str = str(e).lower()
                
                if "rate" in error_str or "quota" in error_str or "resource_exhausted" in error_str or "503" in error_str or "overload" in error_str or "unavailable" in error_str:
                    # Rate limit or overload - try rotating API key first
                    if self._rotate_api_key():
                        logger.info(f"Rotated to new API key, retrying immediately...")
                        time.sleep(1)  # Brief pause before retry with new key
                    else:
                        # No other keys available, wait longer
                        wait_time = self.retry_delay * (attempt + 2)
                        logger.warning(f"Rate limit hit, waiting {wait_time}s...")
                        time.sleep(wait_time)
                elif "invalid" in error_str or "argument" in error_str:
                    # Bad input - log and use fallback
                    logger.error(f"Invalid API input: {e}")
                    return json.dumps({
                        "action": "wait",
                        "target_coordinates": None,
                        "reasoning": f"API input error: {str(e)[:100]}",
                        "updated_candidates": [],
                        "confidence": 0.1,
                        "thought_signature_update": "Error during analysis",
                        "new_detections": 0
                    })
                elif "timeout" in error_str or "deadline" in error_str:
                    # Timeout - retry
                    logger.warning(f"Timeout on attempt {attempt + 1}")
                    time.sleep(self.retry_delay)
                else:
                    # Unknown error - also try rotating key
                    logger.error(f"API error: {e}")
                    if attempt < self.max_retries - 1:
                        # Reduce temperature and retry
                        current_temp = max(0.1, current_temp - 0.1)
                        time.sleep(self.retry_delay)
                    else:
                        raise
        
        # All retries failed - return safe default
        logger.error("All API retries failed")
        return json.dumps({
            "action": "wait",
            "target_coordinates": None,
            "reasoning": "Agent temporarily offline - all API retries failed",
            "updated_candidates": [],
            "confidence": 0.1,
            "thought_signature_update": "Fallback due to API failures",
            "new_detections": 0
        })
    
    def _parse_response(
        self,
        response_text: str,
        context: ContextState
    ) -> AgentDecision:
        """
        Parse and validate the Gemini response.
        
        Args:
            response_text: Raw text response from Gemini
            context: Current context for fallback candidate preservation
        
        Returns:
            Validated AgentDecision
        """
        try:
            # Try to extract JSON from response
            json_str = self._extract_json(response_text)
            
            # Parse JSON
            data = json.loads(json_str)
            
            # Validate with Pydantic
            decision = AgentDecision.model_validate(data)
            
            # Validate slew action has coordinates
            if not decision.validate_slew_action():
                logger.warning("slew_to action missing coordinates, changing to observe_again")
                decision.action = "observe_again"
            
            return decision
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.error(f"=== PARSE FAILURE DETAILS ===")
            logger.error(f"Error position: line {e.lineno}, column {e.colno}, char {e.pos}")
            logger.error(f"Full response length: {len(response_text)}")
            logger.error(f"Response text around error position:")
            # Show context around error
            start = max(0, e.pos - 100) if e.pos else 0
            end = min(len(response_text), (e.pos or 0) + 100)
            logger.error(f"  ...{response_text[start:end]}...")
            logger.error(f"=== FULL RAW RESPONSE ===")
            logger.error(response_text)
            logger.error(f"=== END FULL RESPONSE ===")
            return create_default_wait_decision(
                f"Failed to parse agent response as JSON: {str(e)[:100]}"
            )
        except ValidationError as e:
            logger.error(f"Pydantic validation error: {e}")
            # Try to salvage what we can
            try:
                data = json.loads(self._extract_json(response_text))
                return AgentDecision(
                    action=data.get("action", "wait"),
                    target_coordinates=data.get("target_coordinates"),
                    reasoning=data.get("reasoning", "Partial parse - validation failed"),
                    updated_candidates=context.candidates,  # Preserve existing
                    confidence=data.get("confidence", 0.3),
                    thought_signature_update=data.get("thought_signature_update", ""),
                    new_detections=0
                )
            except Exception:
                return create_default_wait_decision(
                    f"Response validation failed: {str(e)[:100]}"
                )
        except Exception as e:
            logger.error(f"Unexpected parse error: {e}")
            return create_default_wait_decision(f"Unexpected error: {str(e)[:100]}")
    
    def _extract_json(self, text: str) -> str:
        """
        Extract JSON from response text, handling markdown code blocks.
        
        Args:
            text: Raw response text that may contain JSON
        
        Returns:
            Extracted JSON string
        """
        # Try to find JSON in code blocks first
        code_block_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
        ]
        
        for pattern in code_block_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        # Try to find raw JSON object
        # Look for { ... } pattern
        brace_count = 0
        start_idx = None
        
        for i, char in enumerate(text):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx is not None:
                    return text[start_idx:i+1]
        
        # If no JSON found, return the whole text and let JSON parser fail with good error
        return text.strip()
    
    def test_connection(self) -> bool:
        """
        Test the Gemini API connection with a simple query.
        Tries all available API keys before failing.
        
        Returns:
            True if connection successful, False otherwise
        """
        # Try each API key
        for attempt in range(len(self.api_keys)):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents="Say 'SENTINEL ONLINE' if you can read this."
                )
                
                if response.text and "SENTINEL" in response.text.upper():
                    logger.info(f"Gemini connection test: SUCCESS (key {self.current_key_index + 1}/{len(self.api_keys)})")
                    return True
                else:
                    logger.warning(f"Unexpected test response: {response.text}")
                    return True  # Still connected, just unexpected response
                    
            except Exception as e:
                error_str = str(e).lower()
                logger.warning(f"Connection test failed on key {self.current_key_index + 1}: {str(e)[:100]}")
                
                # Try rotating to next key
                if "rate" in error_str or "quota" in error_str or "429" in error_str or "503" in error_str or "overload" in error_str:
                    if self._rotate_api_key():
                        logger.info("Trying next API key...")
                        time.sleep(1)
                        continue
                
                # If we can't rotate, fail
                break
        
        logger.error(f"Gemini connection test FAILED after trying {len(self.api_keys)} key(s)")
        return False


def create_agent(
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> SentinelAgent:
    """
    Factory function to create a SentinelAgent with default settings.
    
    Args:
        api_key: Optional API key (defaults to env var)
        model_name: Optional model name (defaults to env var or default)
    
    Returns:
        Configured SentinelAgent instance
    """
    return SentinelAgent(
        api_key=api_key,
        model_name=model_name,
        temperature=0.2,
        max_retries=3,
        retry_delay=2.0
    )
