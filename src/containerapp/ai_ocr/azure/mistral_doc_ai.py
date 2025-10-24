import json
import base64
import logging
import os
import requests
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_mistral_client_config():
    """Get Mistral Document AI configuration from environment variables"""
    return {
        "endpoint": os.getenv("MISTRAL_ENDPOINT", "https://mistral-demo-foundry-eastus.services.ai.azure.com/providers/mistral/azure/ocr"),
        "api_key": os.getenv("MISTRAL_API_KEY", ""),
        "model": os.getenv("MISTRAL_MODEL", "mistral-document-ai-2505")
    }


def encode_file_to_base64(file_path: str) -> tuple[str, str, str]:
    """
    Encode a file to base64 and determine its MIME type.
    Returns: (base64_string, mime_type, document_type)
    """
    file_extension = Path(file_path).suffix.lower()
    
    # Determine MIME type based on extension
    mime_mapping = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff'
    }
    
    mime_type = mime_mapping.get(file_extension, 'application/pdf')
    document_type = 'document_url' if mime_type == 'application/pdf' else 'image_url'
    
    # Read and encode file
    with open(file_path, 'rb') as f:
        file_content = f.read()
        base64_content = base64.b64encode(file_content).decode('utf-8')
    
    return base64_content, mime_type, document_type


def get_mistral_ocr_results(
    file_path: str, 
    json_schema: Optional[dict] = None,
    include_bbox_annotation: bool = False,
    include_document_annotation: bool = True
) -> str:
    """
    Get OCR results from Mistral Document AI.
    
    Args:
        file_path: Path to the PDF or image file
        json_schema: Optional JSON schema for structured extraction
        include_bbox_annotation: Whether to include bounding box annotations
        include_document_annotation: Whether to include document-level annotations
    
    Returns:
        Extracted text/data from Mistral Document AI
    """
    import threading
    
    thread_id = threading.current_thread().ident
    logger.info(f"[Thread-{thread_id}] Starting Mistral Document AI OCR for: {file_path}")
    
    try:
        # Get configuration
        config = get_mistral_client_config()
        endpoint = config["endpoint"]
        api_key = config["api_key"]
        model = config["model"]
        
        if not api_key:
            raise ValueError("MISTRAL_API_KEY environment variable not set")
        
        # Encode file to base64
        logger.info(f"[Thread-{thread_id}] Encoding file to base64...")
        base64_content, mime_type, document_type = encode_file_to_base64(file_path)
        
        # Construct data URL
        data_url = f"data:{mime_type};base64,{base64_content}"
        
        # Build request payload
        payload = {
            "model": model,
            "document": {
                "type": document_type,
                document_type: data_url
            },
            "include_image_base64": True
        }
        
        # Add document annotation with schema if provided
        if json_schema and include_document_annotation:
            logger.info(f"[Thread-{thread_id}] Adding document annotation format with JSON schema")
            payload["document_annotation_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "schema": json_schema,
                    "name": "document_annotation",
                    "strict": True
                }
            }
        
        # Set up headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Make API request
        logger.info(f"[Thread-{thread_id}] Submitting document to Mistral Document AI API")
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=300  # 5 minute timeout for large documents
        )
        
        # Check response
        if response.status_code != 200:
            error_msg = f"Mistral API error: {response.status_code} - {response.text}"
            logger.error(f"[Thread-{thread_id}] {error_msg}")
            raise Exception(error_msg)
        
        # Parse response
        response_data = response.json()
        logger.info(f"[Thread-{thread_id}] Mistral Document AI OCR completed successfully")
        
        # Extract the relevant content from Mistral response
        # Mistral returns the extracted text/data in the response
        # The structure may vary, so we'll handle multiple formats
        
        if "choices" in response_data and len(response_data["choices"]) > 0:
            # Standard OpenAI-like response format
            choice = response_data["choices"][0]
            if "message" in choice:
                message = choice["message"]
                if "content" in message:
                    content = message["content"]
                    logger.info(f"[Thread-{thread_id}] Extracted {len(content)} characters from Mistral response")
                    return content
        
        # If we have a direct text field
        if "text" in response_data:
            content = response_data["text"]
            logger.info(f"[Thread-{thread_id}] Extracted {len(content)} characters from Mistral response")
            return content
        
        # If we have annotations
        if "annotations" in response_data:
            annotations = response_data["annotations"]
            content = json.dumps(annotations, indent=2)
            logger.info(f"[Thread-{thread_id}] Extracted annotations from Mistral response")
            return content
        
        # Fallback: return entire response as JSON
        logger.warning(f"[Thread-{thread_id}] Unexpected Mistral response format, returning full response")
        return json.dumps(response_data, indent=2)
        
    except Exception as e:
        logger.error(f"[Thread-{thread_id}] Mistral Document AI error: {str(e)}")
        raise Exception(f"Mistral Document AI processing failed: {str(e)}")
