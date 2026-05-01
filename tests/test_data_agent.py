"""
DataAnalysisAgent Tests

Tests code generation, execution, error handling, and answer flow.
Uses MockProvider for deterministic, reproducible behaviour.
"""
import json
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from modules.data_agent import DataAnalysisAgent


class TestCodeGeneration:
    """Code generation: prompt construction and code extraction."""

    def test_generates_code_and_executes(self, sample_dataframes):
        """Normal flow: generate code → execute → return result."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            "result = dfs['sales']['amount'].sum()",
            "Total revenue is $125,000.",
        ]

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("What is total revenue?", sample_dataframes)

        assert result["error"] is None
        assert result["code"] == "result = dfs['sales']['amount'].sum()"
        assert result["result"] is not None

    def test_strips_markdown_code_fences(self, sample_dataframes):
        """Code wrapped in markdown fences → properly stripped."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            "```python\nresult = dfs['sales']['amount'].mean()\n```",
            "Average revenue is $12,500.",
        ]

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("Average revenue?", sample_dataframes)

        assert "```" not in result["code"]
        assert result["code"].strip() == "result = dfs['sales']['amount'].mean()"

    def test_strips_code_fence_without_language(self, sample_dataframes):
        """Code block without language tag → stripped correctly."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            "```\nresult = 42\n```",
            "Result is 42.",
        ]

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("test", sample_dataframes)

        assert result["code"].strip() == "result = 42"


class TestExecution:
    """Code execution: exec environment and result extraction."""

    def test_executes_pandas_operations(self, sample_dataframes):
        """Exec env includes pd, np, px, go."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            "result = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})",
            "Generated a data table.",
        ]

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("Create a table", sample_dataframes)

        assert result["error"] is None
        assert isinstance(result["result"], pd.DataFrame)
        assert result["result"].shape == (3, 2)

    def test_executes_numpy_operations(self, sample_dataframes):
        """Exec env can access numpy."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            "result = np.array([1, 2, 3]).sum()",
            "Result is 6.",
        ]

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("test numpy", sample_dataframes)

        assert result["result"] == 6

    def test_captures_figure_output(self, sample_dataframes):
        """Plotly figures are captured from exec namespace."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            "import plotly.express as px\nfig = px.scatter(x=[1,2,3], y=[4,5,6])",
            "Generated scatter plot.",
        ]

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("Draw scatter", sample_dataframes)

        assert result["error"] is None
        assert result["fig"] is not None


class TestErrorHandling:
    """Error handling: code generation and execution failures."""

    def test_handles_code_generation_error(self, sample_dataframes):
        """LLM code gen fails → returns error message without crashing."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = RuntimeError("API call failed")

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("test", sample_dataframes)

        assert result["error"] is not None

    def test_handles_code_execution_error(self, sample_dataframes):
        """Generated code has bug → retry → still fails → friendly message."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            "result = undefined_variable + 1",    # buggy
            "result = another_undefined + 2",      # still buggy
            "Sorry, data issue.",                  # answer gen
        ]

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("test", sample_dataframes)

        assert result["error"] is not None
        assert result["retry_count"] == 1


class TestAdversarial:
    """Adversarial: dangerous code and malicious input handling."""

    def test_handles_empty_dataframes(self):
        """Empty DataFrames should not crash the agent."""
        empty_data = {"sales": pd.DataFrame(), "waste": pd.DataFrame()}

        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            "result = 'no data'",
            "No data available.",
        ]

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("analyse", empty_data)

        assert result["error"] is None

    def test_handles_large_computation(self, sample_dataframes):
        """Large but finite computation should complete without hanging."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            "result = sum(range(10000))",
            "Done.",
        ]

        with patch("modules.data_agent.get_provider", return_value=mock_provider):
            agent = DataAnalysisAgent()
            result = agent.run("compute", sample_dataframes)

        assert result["error"] is None
        assert result["result"] == sum(range(10000))
