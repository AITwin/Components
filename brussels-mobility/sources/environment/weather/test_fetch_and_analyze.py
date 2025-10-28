import pytest
import requests
from unittest.mock import Mock, patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fetch_and_analyze

def test_main_success():
    """Test successful execution of main function"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "main": {"temp": 15.5, "humidity": 75, "pressure": 1013},
        "weather": [{"main": "Clouds", "description": "overcast clouds"}],
        "wind": {"speed": 5.2, "deg": 180},
        "name": "Brussels"
    }
    
    with patch('requests.get', return_value=mock_response):
        with patch('builtins.print') as mock_print:
            fetch_and_analyze.main()
            assert mock_print.called

def test_main_api_error():
    """Test handling of API errors"""
    with patch('requests.get', side_effect=requests.exceptions.RequestException("API Error")):
        with pytest.raises(requests.exceptions.RequestException):
            fetch_and_analyze.main()
