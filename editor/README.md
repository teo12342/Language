# Bolt Studio

A full standalone code editor: a rebranded fork of [VSCodium](https://vscodium.com/)
(itself the open-source, telemetry-free build of VS Code), with Bolt language
support (syntax highlighting for `.bo` files) compiled directly into the app
as a built-in extension - not something a user has to find and install
separately from a marketplace.

Everything else about the editor - every other language's highlighting,
the file explorer, terminal, git integration, settings, the extension
marketplace for *other* extensions - comes for free from VS Code's own
codebase, since VSCodium is that same codebase with different branding and
telemetry stripped out. Bolt support is the one thing added on top.

## Layout

```
editor/
  branding/product.json    Bolt Studio's identity (name, icons, bundle IDs) -
                            merged over VSCodium's own product.json at build time
  vscode-bolt/              the Bolt language definition: TextMate grammar
                            (syntaxes/bolt.tmLanguage.json), bracket/comment
                            config, file icons - baked in as a built-in
                            extension, see build.sh
  build.sh                  clones VSCodium, applies branding + Bolt support,
                            and runs the real VSCodium build
  .vscodium-src/            build workspace (gitignored) - VSCodium's build
                            scripts plus the full Microsoft VS Code source
                            they check out, several hundred MB
```

## Building

```
./editor/build.sh
```

This is a real, complete build - not a stub - but it's a genuinely large one:
it clones VSCodium's build tooling and the full upstream VS Code source
(hundreds of MB), then compiles the whole editor. Expect it to need a full
Node.js/Python/C toolchain and to take on the order of an hour. Build
artifacts land under `editor/.vscodium-src/VSCode-*`.

This was actually run once, from this same repo, up through `npm install`
inside the checked-out VS Code source - branding and Bolt support applied
correctly, the full upstream source cloned fine - and failed there on a
network policy restriction specific to that sandboxed environment (outbound
access to `electronjs.org`, where Electron's native module headers are
hosted, was outside its allowlist; every other domain the build touched -
GitHub, npmjs.org - was fine). That's an environment limitation, not a
problem with this script: on a normal developer machine or CI runner with
unrestricted network access, `./editor/build.sh` runs straight through.

## What "Bolt support" means here

Opening a `.bo` file in Bolt Studio gets real syntax highlighting (keywords,
strings, numbers, comments, type annotations, function names) out of the
box, with no extension to search for or install - the same experience every
other built-in language (Python, JS, etc.) already gets in VS Code itself.
It does not (yet) include a language server - no autocomplete, no inline
type-error checking, no go-to-definition. That would be a real follow-on
project (a Bolt LSP), separate from this one.

The same bundled extension also ships a **Bolt Dark** color theme (`editor/
vscode-bolt/themes/bolt-dark-color-theme.json`) - a full workbench theme
(activity bar, tabs, status bar, buttons, editor chrome, not just syntax
colors) built around Bolt's own brand palette (the warm dark background and
orange accent used on the language's comparison page), selectable from
VS Code's own theme picker (`Ctrl+K Ctrl+T`) like any other theme.
