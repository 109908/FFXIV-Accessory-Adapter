FF14 Accessory Adapter - remove hardcoded MDL filename restriction

This patch updates Step 2's pending-PMP builder.

What changes:
- Removes the hard-coded requirement that the selected target MDL filename must be
  c0501e6047_met.mdl or c0601e6047_met.mdl.
- Infers the model resource path from the selected source mod's Files mappings.
- Supports standard equipment/accessory item paths such as e6047 and a0047.
- Accepts renamed input MDL files (for example yuananjing_ear.mdl) when the selected
  option group has a single inferable model family in its Files mappings.
- Refuses ambiguous groups with multiple distinct model families rather than guessing.

Install:
1. Close the EXE.
2. Back up the project folder.
3. Extract this ZIP into the project root, preserving folders; overwrite prompted files.
4. Run: .\.venv\Scripts\python.exe -m unittest discover -s tests -v
5. Rebuild: .\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm .\FF14-Accessory-Adapter.spec

Important:
This removes the filename gate; it does not prove the selected MDL bytes are the correct
vanilla target model. The model path is inferred from the original mod's Files mapping.
The chosen MDL must still be the intended target-race base model, and the final PMP must
be imported/saved in Penumbra and tested in-game.
