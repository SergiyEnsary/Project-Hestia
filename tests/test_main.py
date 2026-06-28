from unittest.mock import patch

from hestia.main import main


def test_main_no_command_prints_help(capsys):
    with patch("sys.argv", ["hestia"]):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1
    captured = capsys.readouterr()
    assert "hestia" in captured.out.lower() or "serve" in captured.out.lower()


def test_main_serve_invokes_uvicorn():
    with patch("hestia.main.uvicorn.run") as mock_run, patch("sys.argv", ["hestia", "serve"]):
        main()
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs.get("factory") is True
