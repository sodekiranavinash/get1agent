"""Test MCP Gateway functionality in admin-console."""

import os
import json
from unittest.mock import patch, MagicMock
import sys

# Add packages directory to path to import core and data modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../packages"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_mcp_transport_gateway_with_url():
    """Test that _mcp_transport returns 'gateway' when configured correctly."""
    import handler
    
    # Test with gateway transport and URL
    os.environ["MCP_TRANSPORT"] = "gateway"
    os.environ["MCP_GATEWAY_URL"] = "https://example.com/gateway"
    
    result = handler._mcp_transport()
    assert result == "gateway"
    
    # Cleanup
    del os.environ["MCP_TRANSPORT"]
    del os.environ["MCP_GATEWAY_URL"]

def test_mcp_transport_gateway_without_url_falls_back():
    """Test that _mcp_transport falls back to aggregator when gateway URL missing."""
    import handler
    
    # Test with gateway transport but no URL
    os.environ["MCP_TRANSPORT"] = "gateway"
    
    result = handler._mcp_transport()
    assert result == "aggregator"
    
    # Cleanup
    del os.environ["MCP_TRANSPORT"]

def test_mcp_transport_aggregator():
    """Test that _mcp_transport returns 'aggregator' by default."""
    import handler
    
    # Test default behavior
    result = handler._mcp_transport()
    assert result == "aggregator"

def test_gateway_url():
    """Test _gateway_url returns correct URL."""
    import handler
    
    os.environ["MCP_GATEWAY_URL"] = "https://example.com/gateway"
    
    result = handler._gateway_url()
    assert result == "https://example.com/gateway"
    
    # Cleanup
    del os.environ["MCP_GATEWAY_URL"]

def test_gateway_url_none_when_not_set():
    """Test _gateway_url returns None when not configured."""
    import handler
    
    result = handler._gateway_url()
    assert result is None

def test_handle_list_tools_gateway_mode():
    """Test _handle_list_tools in gateway mode."""
    import handler
    
    # Patch the imported function directly in handler module
    with patch('handler.gateway_list_tools') as mock_gateway_list_tools:
        # Mock gateway response
        mock_tools_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "knowledge___search-user-knowledge-bases",
                        "description": "Search knowledge bases",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "code-interpreter___code-interpreter",
                        "description": "Execute code",
                        "inputSchema": {"type": "object", "properties": {}}
                    }
                ]
            }
        }
        mock_gateway_list_tools.return_value = mock_tools_response
        
        # Mock _json function  
        with patch.object(handler, '_json') as mock_json:
            mock_json.return_value = {"statusCode": 200, "body": "test"}
            
            # Call handler
            result = handler._handle_list_tools(
                functions=["test-function"], 
                user_id="test-user",
                region="us-east-1",
                transport="gateway",
                gateway_url="https://example.com/gateway",
                session_id="test-session"
            )
            
            # Verify gateway_list_tools was called with correct args
            mock_gateway_list_tools.assert_called_once_with(
                "https://example.com/gateway",
                "test-session",
                "us-east-1"
            )
            
            # Verify _json was called with correct response structure
            call_args = mock_json.call_args[0]
            assert call_args[0] == 200
            response_body = call_args[1]
            assert response_body["ok"] is True
            assert response_body["gatewayMode"] is True

def test_handle_call_tool_gateway_mode():
    """Test _handle_call_tool in gateway mode."""
    import handler
    
    with patch('handler.gateway_list_tools') as mock_gateway_list_tools, \
         patch('handler.gateway_call_tool') as mock_gateway_call_tool, \
         patch.object(handler, '_json') as mock_json:
        
        # Mock gateway list tools response
        mock_list_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "knowledge___search-user-knowledge-bases",
                        "description": "Search knowledge bases"
                    }
                ]
            }
        }
        mock_gateway_list_tools.return_value = mock_list_response
        
        # Mock gateway call tool response
        mock_call_response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "content": [{"type": "text", "text": "test result"}]
            }
        }
        mock_gateway_call_tool.return_value = mock_call_response
        
        # Mock _json function
        mock_json.return_value = {"statusCode": 200, "body": "test"}
        
        # Call handler
        result = handler._handle_call_tool(
            functions=["test-function"],
            user_id="test-user",
            region="us-east-1",
            body={"name": "search-user-knowledge-bases", "arguments": {"query": "test"}},
            transport="gateway",
            gateway_url="https://example.com/gateway",
            session_id="test-session"
        )
        
        # Verify gateway_list_tools was called
        mock_gateway_list_tools.assert_called_once_with(
            "https://example.com/gateway",
            "test-session",
            "us-east-1"
        )
        
        # Verify gateway_call_tool was called with correct args
        mock_gateway_call_tool.assert_called_once_with(
            "https://example.com/gateway",
            "test-session",
            "knowledge___search-user-knowledge-bases",
            {"query": "test"},
            "us-east-1"
        )
        
        # Verify _json was called
        call_args = mock_json.call_args[0]
        assert call_args[0] == 200
        response_body = call_args[1]
        assert response_body["ok"] is True
        assert response_body["server"] == "knowledge"

def test_handle_call_tool_gateway_mode_tool_not_found():
    """Test _handle_call_tool when tool is not found in gateway."""
    import handler
    
    with patch('handler.gateway_list_tools') as mock_gateway_list_tools, \
         patch.object(handler, '_json') as mock_json:
        
        # Mock gateway list tools response (empty)
        mock_list_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []}
        }
        mock_gateway_list_tools.return_value = mock_list_response
        
        # Mock _json function
        mock_json.return_value = {"statusCode": 200, "body": "test"}
        
        # Call handler
        result = handler._handle_call_tool(
            functions=["test-function"],
            user_id="test-user",
            region="us-east-1",
            body={"name": "non-existent-tool", "arguments": {}},
            transport="gateway",
            gateway_url="https://example.com/gateway",
            session_id="test-session"
        )
        
        # Verify the response indicates tool not found
        call_args = mock_json.call_args[0]
        assert call_args[0] == 200
        response_body = call_args[1]
        assert response_body["ok"] is False
        assert "not found" in response_body["error"]["message"]

if __name__ == "__main__":
    # Run tests
    test_mcp_transport_gateway_with_url()
    print("✓ test_mcp_transport_gateway_with_url passed")
    
    test_mcp_transport_gateway_without_url_falls_back()
    print("✓ test_mcp_transport_gateway_without_url_falls_back passed")
    
    test_mcp_transport_aggregator()
    print("✓ test_mcp_transport_aggregator passed")
    
    test_gateway_url()
    print("✓ test_gateway_url passed")
    
    test_gateway_url_none_when_not_set()
    print("✓ test_gateway_url_none_when_not_set passed")
    
    test_handle_list_tools_gateway_mode()
    print("✓ test_handle_list_tools_gateway_mode passed")
    
    test_handle_call_tool_gateway_mode()
    print("✓ test_handle_call_tool_gateway_mode passed")
    
    test_handle_call_tool_gateway_mode_tool_not_found()
    print("✓ test_handle_call_tool_gateway_mode_tool_not_found passed")
    
    print("\nAll tests passed!")