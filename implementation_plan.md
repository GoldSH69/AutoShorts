# Dynamic Thumbnail Hook Generation and Enhanced Title Styling

Make the thumbnail hook more natural and engaging by letting Gemini dynamically generate it in context, and increase the thumbnail subtitle's font size so it functions as a prominent cover title.

## Proposed Changes

### Configuration Prompts
We will update the `"thumbnail_hook"` JSON schema guideline in all prompt files to allow dynamic generation.

- [brain.txt](file:///d:/Work/AI/AutoShorts/config/prompts/brain.txt)
- [dark.txt](file:///d:/Work/AI/AutoShorts/config/prompts/dark.txt)
- [hack.txt](file:///d:/Work/AI/AutoShorts/config/prompts/hack.txt)
- [love.txt](file:///d:/Work/AI/AutoShorts/config/prompts/love.txt)
- [money.txt](file:///d:/Work/AI/AutoShorts/config/prompts/money.txt)
- [relationship.txt](file:///d:/Work/AI/AutoShorts/config/prompts/relationship.txt)
- [success.txt](file:///d:/Work/AI/AutoShorts/config/prompts/success.txt)

Change the JSON format line:
```json
-  "thumbnail_hook": "지정된 썸네일 후킹 문구 ({thumbnail_hook})",
+  "thumbnail_hook": "대본 내용과 호응하며 시청자의 호기심을 극대화하는 썸네일용 초압축 후킹 문구 (10자 내외, '{thumbnail_hook}'를 참고하여 창작하되 더 직관적이고 자극적으로 작성)",
```

---

### Scripts Component

#### [script_generator.py](file:///d:/Work/AI/AutoShorts/scripts/script_generator.py)
- Implement a helper method `_clean_thumbnail_hook(self, hook, fallback)` to clean any brackets or template residue (e.g. the text "지정된 썸네일 후킹 문구") and fall back to the static topic hook if needed.
- Modify the logic that enforces the hook to allow Gemini's cleaned hook.

```python
    def _clean_thumbnail_hook(self, hook, fallback):
        if not hook:
            return fallback
        hook = hook.strip()
        # Remove template residue if model copied it literally
        if "지정된 썸네일 후킹 문구" in hook:
            import re
            match = re.search(r'\((.*?)\)', hook)
            if match:
                hook = match.group(1).strip()
            else:
                hook = hook.replace("지정된 썸네일 후킹 문구", "").strip()
        
        # Strip common quotation marks and brackets
        hook = hook.strip('\'"()[]{}👉 \t\n')
        return hook or fallback
```

Replace lines where the static hook is unconditionally written:
```python
-        result['thumbnail_hook'] = self.selected_thumbnail_hook
+        result['thumbnail_hook'] = self._clean_thumbnail_hook(result.get('thumbnail_hook', ''), self.selected_thumbnail_hook)
```

#### [subtitle_generator.py](file:///d:/Work/AI/AutoShorts/scripts/subtitle_generator.py)
- Introduce a new `Title` style in the ASS template with `1.4x` font size, bold, and larger outline/shadow sizes.
- Render the 0.0s - 0.3s `thumbnail_hook` subtitle using the `Title` style.

```diff
 [V4+ Styles]
 Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
 Style: Default,{font_name},{font_size},{font_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline_width},{shadow_offset},{alignment},50,50,{margin_v},1
 Style: Highlight,{font_name},{int(font_size*1.1)},&H0000D4FF,&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{int(outline_width+1)},{shadow_offset},{alignment},50,50,{margin_v},1
+Style: Title,{font_name},{int(font_size*1.4)},&H0000D4FF,&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{int(outline_width*1.5)},{int(shadow_offset*1.5)},{alignment},50,50,{margin_v},1
```

```diff
-            events += f"Dialogue: 0,{start_str},{end_str},Highlight,,0,0,0,,{display_text}\n"
+            events += f"Dialogue: 0,{start_str},{end_str},Title,,0,0,0,,{display_text}\n"
```

---

## Verification Plan

### Automated / Semi-automated Tests
- Run `python scripts/main.py --no-history --category money` (or success/brain/etc.) to generate a test script and check the output logs and generated `.ass` subtitles file.
- Inspect the generated `.ass` file under the `output/` directory to verify the `Title` style is added and used properly for the first 0.3 seconds.
- Verify that the Gemini-generated `thumbnail_hook` is logged and used instead of the exact `topics.json` string.
