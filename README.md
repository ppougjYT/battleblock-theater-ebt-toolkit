# EBT Toolkit

This folder contains the Python files needed to export, edit, verify, and rebuild a BattleBlock Theater playlist `.ebt`.

This version is meant to be shareable. It does not depend on any personal file path.

## Use This Folder As The Root

Put these files and folders directly inside the same folder as this README:

- `hexdump_playlist_tool.py`
- `bbt_level_tool.py`
- `rebuild_ebt.py`
- `key1`
- `key2`
- `Playlists\HexDump.txt`
- `Playlists\Campaign1.ebt`

The process will create:

- `playlist_edit\`
- `Playlists\HexDump_rebuilt.txt`
- `Playlists\Campaign1_edited.ebt`
- `Playlists\Campaign1_backup.ebt`

## How To Use It

1. Open PowerShell in this folder.
2. Run the commands below in order.
3. Edit the JSON files in `.\playlist_edit\` after the export step.

## PowerShell Commands

### 1. Export the playlist into editable JSON

```powershell
python .\hexdump_playlist_tool.py export .\Playlists\HexDump.txt .\playlist_edit
```

### 2. Edit the JSON files

Edit the files inside:

```text
.\playlist_edit\
```

Important:

- Keep the same `width` and `height` unless you know exactly what you are changing.
- Keep each tile row the same length.
- Do not remove fields from the JSON.

### 3. Verify the edited JSON

```powershell
python .\hexdump_playlist_tool.py verify .\playlist_edit --template .\Playlists\HexDump.txt
```

### 4. Rebuild the raw playlist dump

```powershell
python .\hexdump_playlist_tool.py import .\playlist_edit .\Playlists\HexDump_rebuilt.txt --template .\Playlists\HexDump.txt
```

### 5. Rebuild the final `.ebt`

```powershell
python .\rebuild_ebt.py .\Playlists\HexDump_rebuilt.txt .\Playlists\Campaign1.ebt .\Playlists\Campaign1_edited.ebt
```

### 6. Back up the original and replace it

```powershell
Copy-Item .\Playlists\Campaign1.ebt .\Playlists\Campaign1_backup.ebt
Copy-Item .\Playlists\Campaign1_edited.ebt .\Playlists\Campaign1.ebt
```

## Restore Original

If you want to undo the change:

```powershell
Copy-Item .\Playlists\Campaign1_backup.ebt .\Playlists\Campaign1.ebt
```

## Notes

- `HexDump.txt` is the raw playlist dump used as the editable template.
- `Campaign1.ebt` is the original encrypted playlist used as the rebuild template.
- If you want to adapt this to a different playlist, swap in the matching dump file and `.ebt` file.
