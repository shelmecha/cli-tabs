# cli-tabs

Shows the state of each Claude Code session on its Windows Terminal tab. While Claude works, the tab shows the Claude loading star (`· ✢ ✶ ✻ ✽`), animated. When Claude is done or waits for you, the tab shows a check (`✓`).

```
✻ agent-dave        Claude works
✓  cli-tabs         Claude is done, or waits for your answer or permission
```

Status: finished. Tested on 2026-10-06 with Claude Code 2.1.291, Windows Terminal and Python 3.14 on Windows 11.

## Requirements

- Windows 10 or 11 with Windows Terminal.
- Claude Code 2.1.291 or later. This is the version we tested.
- Python 3 on the `PATH` as `python`. The script uses only the standard library.

## Install

1. Clone the repo:

   ```
   git clone https://github.com/shelmecha/cli-tabs.git
   ```

2. Open `%USERPROFILE%\.claude\settings.json`. Make a copy of it first.
3. Add the `env` value and the 8 hooks from [`hooks.example.json`](hooks.example.json). Keep your other hooks. Replace `C:/path/to/cli-tabs` with the folder of the clone.
4. Start a new Claude Code session. Claude Code reads the `env` value only at startup.

The env value `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` stops Claude Code from writing its own tab title (`◐` and `✳`). Without it, Claude Code writes over the star and the check.

## Name a tab

The tab shows the session name, or the folder name if the session has no name.

- To name a new session: `claude -n dave`
- To name a running session: `/rename dave`. The new name shows at the next state change.

Do not use "Rename tab" in Windows Terminal. After that rename, Windows Terminal ignores all titles from the program, so the tab cannot show the star or the check. To remove a Windows Terminal name, right-click the tab, select **Rename tab**, delete the text and press Enter.

## Themes

Write the theme name on the first line of [`theme.txt`](theme.txt). The next state change uses the new theme.

| Theme | Working | Done |
|---|---|---|
| `claude` (default) | `· ✢ ✶ ✻ ✽` animated | `✓` |
| `circles` | 🟡 | 🟢 |
| `hearts` | 💛 | 💚 |
| `moon` | 🌑 🌒 🌓 🌔 🌕 animated | ✨ |
| `sprout` | 🌱 | 🌸 |
| `chick` | 🥚 | 🐣 |

## Optional: hide the PowerShell icon

The tab icon shows before the title. To put the star or the check at the start of the tab, hide the icon. In the Windows Terminal `settings.json`, set the profile `icon` to a zero-width space:

```json
"icon": "\u200b"
```

The value `"none"` does not hide the icon. Only new tabs use the change.

## How it works

- Claude Code starts `tab_status.py` from its hooks. The hooks run in the background (`"async": true`), so Claude does not wait for them.
- Hook commands run in a hidden console. A title from a hook does not get to the tab. The script finds the parent `claude.exe`, attaches to its console and sets the title there with `SetConsoleTitleW`.
- For an animated theme, the script starts one background process per session. That process changes the frame every 0.12 seconds. It stops when the state is not "working" or when `claude.exe` stops.
- The state of each session is in `%TEMP%\cli-tabs\<session id>.json`.
- A `PostToolUse` hook can arrive after `Stop`. The script ignores a "working" from `PostToolUse` for 3 seconds after "done".
- The script also clears the Windows Terminal progress ring (`OSC 9;4`). To stop the ring from Claude Code, set `"terminalProgressBarEnabled": false` in `settings.json`.

| Hook | State |
|---|---|
| `SessionStart` | done (`wait`) |
| `UserPromptSubmit` | working |
| `PostToolUse` | working (`tool`) |
| `PermissionRequest` | done (`wait`) |
| `Notification` (`permission_prompt`, `elicitation_dialog`) | done (`wait`) |
| `Stop`, `StopFailure` | done |
| `SessionEnd` | plain name (`end`) |

## Limits

- After you approve a permission, the tab shows the check until the tool is complete.
- `/rename` does not start a hook. The new name shows at the next state change.
- Sessions that started before the install keep the Claude Code title until you restart them.

## Uninstall

1. Remove the 8 `tab_status.py` hooks and the `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` value from `settings.json`.
2. Start a new Claude Code session.
3. You can delete the `%TEMP%\cli-tabs` folder.

## License

MIT
