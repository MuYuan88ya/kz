# Repository Guidelines

## Project Structure & Module Organization

This repository is a small script-based Python project for bridging a Kaggle notebook and a Windows client through `zrok` and SSH.

- `zrok_server.py`: Kaggle-side startup, persisted state, SSH bootstrap, and devtools launch.
- `zrok_client.py`: Windows-side access tunnel, SSH readiness checks, VS Code setup, and auth sync.
- `utils.py`: shared `zrok` helpers used by both sides.
- `prepare_client.bat`, `start_client.bat`: Windows entry points for first-time setup and daily use.
- `setup_ssh.sh`, `setup_devtools.sh`: Kaggle/Linux provisioning scripts.
- `test_*.py`: lightweight manual validation scripts.
- `images/`: documentation assets.

## Build, Test, and Development Commands

Use Python 3.11+. `uv.lock` is present, so prefer `uv` where available.

- `uv sync`: create/update the local virtual environment.
- `uv run python zrok_client.py --help`: inspect client CLI options.
- `uv run python zrok_server.py --help`: inspect Kaggle-side CLI options.
- `.\prepare_client.bat`: generate or reuse the local SSH key and print the Kaggle init command.
- `.\start_client.bat`: open local zrok access and start the Windows client flow.
- `.\.venv\Scripts\python.exe -m py_compile utils.py zrok_client.py zrok_server.py`: fast syntax check before committing.
- `python test_wait.py` or `python test_ssh.py`: manual SSH readiness checks on Windows.

## Coding Style & Naming Conventions

Follow the existing style in the repository:

- 4-space indentation, UTF-8 text, and straightforward standard-library Python.
- `snake_case` for functions, variables, and filenames; `UPPER_CASE` for constants.
- Keep scripts single-purpose and avoid adding heavy dependencies unless necessary.
- Preserve cross-platform path handling with `pathlib.Path` and explicit encoding/newline control when writing files.

## Testing Guidelines

There is no formal `pytest` suite yet. Add focused `test_*.py` scripts near the repo root for new runtime checks, and keep them executable with plain `python`. Validate both paths you touch: Windows client flow and Kaggle server flow when applicable.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit prefixes such as `feat:` and `fix:`. Keep subjects short and imperative, for example `fix: wait for ssh login before opening vscode`.

Pull requests should include:

- a short problem statement and the changed flow
- manual validation steps or command output
- linked issue/context when relevant
- screenshots only for documentation or UX-facing changes

## Security & Configuration Tips

Do not commit real `zrok` tokens, SSH private keys, or machine-specific config. Treat `%USERPROFILE%\.kaggle_remote_zrok`, `%USERPROFILE%\.ssh`, and `/kaggle/working/.kaggle_remote_zrok` as sensitive state directories.
