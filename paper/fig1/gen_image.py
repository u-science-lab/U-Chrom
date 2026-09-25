"""Generate an image with an OpenRouter image model; saves PNG(s).

    python gen_image.py OUT_PREFIX "prompt" [--model openai/gpt-5.4-image-2]
Reads OPENROUTER_API_KEY from the environment (source ~/.env).
"""
import argparse, base64, json, os, sys, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("out"); ap.add_argument("prompt")
ap.add_argument("--model", default="openai/gpt-5.4-image-2")
ap.add_argument("--image", help="optional reference image to edit")
a = ap.parse_args()
content = [{"type": "text", "text": a.prompt}]
if a.image:
    b64 = base64.b64encode(open(a.image, "rb").read()).decode()
    content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
body = {"model": a.model, "modalities": ["image", "text"], "messages": [{"role": "user", "content": content}]}
req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                             headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                                      "Content-Type": "application/json"})
r = json.load(urllib.request.urlopen(req, timeout=600))
msg = r["choices"][0]["message"]
imgs = msg.get("images") or []
for i, im in enumerate(imgs):
    url = im["image_url"]["url"]
    data = base64.b64decode(url.split(",", 1)[1])
    path = f"{a.out}_{i}.png" if len(imgs) > 1 else f"{a.out}.png"
    open(path, "wb").write(data); print(path, len(data))
if not imgs:
    print("no image; text:", (msg.get("content") or "")[:500], file=sys.stderr); sys.exit(1)
print("cost:", r.get("usage", {}).get("cost"))
