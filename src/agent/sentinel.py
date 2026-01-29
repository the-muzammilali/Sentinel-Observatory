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
from .prompts import build_full_prompt, SYSTEM_INSTRUCTION

# Configure logging
logger = logging.getLogger(__name__)


class SentinelAgent:
    """
    Gemini-powered autonomous astronomical agent.
    
    This agent implements the DECIDE phase of the OODA loop:
    - Receives telescope images and context state
    - Analyzes images using Gemini vision capabilities
    - Outputs structured decisions for transient detection
    
    Attributes:
        client: Gemini API client
        model_name: Name of the Gemini model to use
        temperature: Sampling temperature (lower = more deterministic)
        max_retries: Maximum retry attempts on failure
        retry_delay: Base delay between retries in seconds
    """
    
    DEFAULT_MODEL = "gemini-2.0-flash"
    MAX_IMAGE_SIZE = 4096  # Gemini max dimension
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.2,
        max_retries: int = 3,
        retry_delay: float = 2.0
    ):
        """
        Initialize the Sentinel Agent.
        
        Args:
            api_key: Google API key. If None, loads from GOOGLE_API_KEY env var.
            model_name: Gemini model name. Defaults to gemini-2.0-flash.
            temperature: Sampling temperature (0.0-1.0). Lower = more consistent.
            max_retries: Maximum API retry attempts.
            retry_delay: Base delay between retries in seconds.
        """
        # Load environment variables
        load_dotenv()
        
        # Get API key
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY not found. Set it in .env file or pass api_key parameter."
            )
        
        # Initialize Gemini client
        self.client = genai.Client(api_key=self.api_key)
        
        # Model configuration
        self.model_name = model_name or os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL)
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        logger.info(f"SentinelAgent initialized with model: {self.model_name}")
    
    def analyze_images(
        self,
        reference: np.ndarray,
        current: np.ndarray,
        diff_annotated: np.ndarray,
        context: ContextState
    ) -> AgentDecision:
        """
        Analyze telescope images and make a decision.
        
        This is the main entry point for the agent. It:
        1. Prepares images for the API
        2. Builds the prompt with context
        3. Calls Gemini with retry logic
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
        
        # Prepare images
        try:
            images = self._prepare_images(reference, current, diff_annotated)
        except Exception as e:
            logger.error(f"Image preparation failed: {e}")
            return create_default_wait_decision(f"Image preparation error: {e}")
        
        # Build prompt
        prompt = build_full_prompt(context, include_examples=True)
        
        # Call Gemini with retry
        response_text = self._call_gemini_with_retry(prompt, images)
        
        # Parse response
        decision = self._parse_response(response_text, context)
        
        logger.info(f"Decision: {decision.action} (confidence: {decision.confidence:.2f})")
        return decision
    
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
                    max_output_tokens=4096,
                    candidate_count=1,
                    response_mime_type="application/json",  # Force valid JSON output
                )
                
                # Make API call
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config
                )
                
                # Extract text
                if response.text:
                    return response.text
                else:
                    logger.warning("Empty response from Gemini")
                    raise ValueError("Empty response received")
                
            except Exception as e:
                error_str = str(e).lower()
                
                if "rate" in error_str or "quota" in error_str or "resource_exhausted" in error_str:
                    # Rate limit - wait longer
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
                    # Unknown error
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
            logger.debug(f"Raw response: {response_text[:500]}")
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
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents="Say 'SENTINEL ONLINE' if you can read this."
            )
            
            if response.text and "SENTINEL" in response.text.upper():
                logger.info("Gemini connection test: SUCCESS")
                return True
            else:
                logger.warning(f"Unexpected test response: {response.text}")
                return True  # Still connected, just unexpected response
                
        except Exception as e:
            logger.error(f"Gemini connection test FAILED: {e}")
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
