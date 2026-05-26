# Deploying chat_cad to Hugging Face Spaces

Hugging Face Spaces (Docker SDK) gives you a free public URL like
`https://huggingface.co/spaces/<you>/chat-cad` that you can link from
samarjithbiswas.com. Visitors paste their own Anthropic API key into the
UI — no shared key is needed and nothing of yours is stored.

## One-time setup

1. Sign in at https://huggingface.co (free).
2. Click **New Space** → name it `chat-cad` → SDK = **Docker** → Hardware =
   *CPU basic (free)* → visibility = Public.
3. HF will give you a git URL like `https://huggingface.co/spaces/<you>/chat-cad`.

## Push the code

From this folder (`chat_cad/`):

```powershell
git init
git add .
git commit -m "Initial chat_cad Space"
git branch -M main
git remote add origin https://huggingface.co/spaces/<you>/chat-cad
git push -u origin main
```

You'll be prompted for HF credentials — use a write token from
https://huggingface.co/settings/tokens (User Access Token, Write scope).

## Add the Space metadata

At the top of `README.md` in the Space repo, prepend this YAML block so HF
treats it as a Docker Space and uses port 7860:

```yaml
---
title: Chat CAD
emoji: 🧱
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---
```

(HF requires the front-matter; everything below it is the visible page.)

## First build

The first build takes ~5–8 minutes — conda pulls OpenCascade. Watch
progress in the Space's **Logs** tab. When the log says
`Running on http://0.0.0.0:7860`, the UI is live at the Space URL.

## Linking from samarjithbiswas.com

Add a card to your website similar to PhononIQ / SAWNet:

```html
<a href="https://huggingface.co/spaces/<you>/chat-cad" class="project-card">
  <h3>chat_cad</h3>
  <p>Chat-driven parametric CAD with a real OpenCascade kernel.</p>
</a>
```

## Updating later

```powershell
git add .
git commit -m "describe change"
git push
```

The Space auto-rebuilds on push.

## Notes / limits

- The free CPU tier has 16 GB RAM and shuts down after 48 h of inactivity;
  it wakes on first request (cold-start ~30 s while the Docker image boots).
- Each visitor's session is in-process. There's no multi-user isolation —
  if two people use the Space at the same time they share the scene.
  Spin up a dedicated process per session (Flask `before_request`) if that
  matters; for a portfolio demo it usually doesn't.
- Visitor API keys are sent to the Space's backend in the `/chat` POST.
  They are NOT logged or persisted. Make this clear in the UI's settings
  panel before going public.
