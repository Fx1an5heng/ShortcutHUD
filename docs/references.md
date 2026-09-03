# Design References

These notes capture reusable interaction principles, not product parity or
implementation dependencies.

## Microsoft Office KeyTips

Reference: [Use the keyboard to work with the ribbon](https://support.microsoft.com/en-gb/office/use-the-keyboard-to-work-with-the-ribbon-954cd3f7-2f77-4983-978d-c09b20e31f0e)

Borrow:

- progressive disclosure instead of showing every command at once;
- hierarchical navigation that reveals the next relevant choices;
- a clear escape path for returning or cancelling.

Do not borrow:

- taking over `Alt` as ShortcutHUD's central trigger;
- automatically executing commands selected through the guide.

## PowerToys Shortcut Guide

Reference: [PowerToys Shortcut Guide](https://learn.microsoft.com/en-us/windows/powertoys/shortcut-guide)

Borrow:

- an active-application shortcut reference;
- user control over activation behavior and timing;
- application exclusion and contextual suppression as product concepts.

The distinction between fullscreen `SOFT_BLOCK` and explicit exclusion
`HARD_BLOCK` is ShortcutHUD's own policy decision.

## which-key

Reference: [which-key.nvim](https://github.com/folke/which-key.nvim)

Borrow:

- prefix-based discovery;
- hierarchical exploration of the remaining valid keys;
- `Backspace` for moving up and `Esc` for leaving the interaction.

## KeyCue

Reference: [How to start with KeyCue](https://help.keycue.ergonis.com/hc/en-us/articles/23090906791452-How-to-start-with-KeyCue)

Borrow:

- a full shortcut reference scoped to the active application;
- explicit, user-controlled invocation for a larger guide surface.
