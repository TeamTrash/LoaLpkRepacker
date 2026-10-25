# LoaLpkRepacker

A fan-made Windows tool for rebuilding compatible Lost Ark LPK archives from an original archive and its complete extracted folder.

Repack your edited files into a **new LPK** with built-in integrity checks. The tool leaves your original archive and source files unchanged and does not automatically install the result into the game.

**Current version: 0.2.1**

## How it works

**Original LPK → complete extracted folder → new verified LPK**

The original archive provides the structure, and the extracted folder provides the contents. Only changed entries are re-encrypted. Unchanged entries retain their original encrypted bytes.

This application does not extract archives or edit databases. Prepare your extracted files and edits separately.

## Requirements

- Windows x64.
- .NET 8 Runtime x64.
- An intact original LPK and its matching, complete extracted folder.
- Enough free disk space for temporary working files and the new archive.

Python is included in the packaged executable and does not need to be installed separately.

## Usage

1. Save your edits and close any database editors.
2. Open `LoaLpkRepacker-0.2.1.exe`.
3. Select the **original LPK**.
4. Select its **complete extracted folder**.
5. Choose a **new output filename** ending in `.lpk`, outside the extracted folder.
6. Start repacking and wait for verification to finish.

The folder can have any name, but internal filenames and paths must match the archive. Keep all extracted files, including unmodified ones. Use an original archive and extraction from the same game version.

On success, the tool saves the new archive and a verification report alongside it:

```text
data2_repacked.lpk
data2_repacked.lpk.verification.json
```

Existing output files are not overwritten. Operations can be cancelled before the result is published.

## Verification

The tool checks folder contents, creates a temporary working copy, checks for source changes during copying, and validates SQLite integrity. Missing, extra, empty or ambiguous files and pending SQLite WAL/journal files are rejected.

Before publishing the result, it decrypts every output entry and compares its SHA-256 with the working copy. It also checks that unchanged entries retain their original encrypted bytes. A JSON report records the verification and output SHA-256.

For the supported SQLite layout, the working copy includes the padding correction described below. Input files remain unchanged.

## Compatibility and limitations

- Validated with a `data2.lpk` sample containing 990 SQLite databases; compatibility with every archive or game update is not guaranteed.
- Requires an existing compatible archive. It cannot build an LPK from an arbitrary folder or add or remove entries.
- Rejects `.db` files that are not SQLite and folders containing symbolic links or junctions.
- Filenames must be preserved because they are involved in database encryption.
- Integrity checks do not validate translations or guarantee that edited content displays correctly in the game.

Version 0.2.1 received an initial user report of successful in-game use. This is not exhaustive compatibility testing.

## Version 0.2.1: SQLite padding fix

Some database editors create new pages with zero-filled reserved bytes. For the known layout with 1,024-byte SQLite pages and 16 reserved bytes, this version restores the expected encryption padding **in the temporary copy only**. The backend checks the original archive's padding convention independently.

Useful SQLite data and text remain unchanged. SHA-256 comparisons use the normalized working copy, and the report records repaired pages under `padding_repairs`. Use an intact original archive, not a faulty repack from an earlier version.

## Development

The interface uses Python/Tkinter. The backend is `LpkBulkRepack`, based on the local `lostark-explorer` Core reference.

These commands assume the full research workspace, including `tools/LpkBulkRepack` and its dependencies. The application folder alone is not a standalone build distribution.

Run tests from the workspace root:

```powershell
python -m unittest discover -s apps/LoaLpkRepacker -p test_app.py
```

Build with Python, PyInstaller and the .NET 8 SDK installed, and backend dependencies already restored:

```powershell
python apps/LoaLpkRepacker/build_windows.py
```

Output:

```text
apps/releases/LoaLpkRepacker/0.2.1/LoaLpkRepacker-0.2.1.exe
```

## Feedback

Include the application version, error message and archive type when reporting a problem. Review verification reports before sharing them: they contain local file paths. Do not attach game archives or databases.

## Credits

An independent fan project, not affiliated with or endorsed by Lost Ark, Smilegate or Amazon Games. Third-party components retain their respective licenses. This README grants no redistribution rights for those components or game content.
