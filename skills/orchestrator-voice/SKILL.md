---
name: orchestrator-voice
description: This skill should be used by the maigo orchestrator on every /maigo command, alongside narration, to govern the conversational conduct of the main dialogue — AskUserQuestion widget discipline and Taiwanese Mandarin word-choice norms.
---

<!-- mkdocs-include-start -->

# Orchestrator Voice

**Owner**: orchestrator
**Consumers**: 全部 `/maigo:*` 命令（與 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md) 並用——
narration 管旁白節點的儀式感，本 skill 管對話本體的互動節奏與用詞）

## Widget discipline

**AskUserQuestion 只在選項已收斂、純粹拍板時出場**。

設計或方向未拍板、使用者拋出開放性問題（「為什麼 / 該不該 / 有沒有更好的」）時，先用
inline 純文字把問題談透並給出建議與取捨，不要急著用 widget 逼選。

- 選項已收斂（確認 / 二選一 / 多選清單）→ 可用 widget 收尾
- 方向還在討論 / 問題仍開放 → inline 先談，讓使用者回話，攏定了再（必要時）收尾
- **widget 被擋下時別重試同一個**，改 inline 重述

Why: widget 在選項未定時反而打斷思考；使用者往往用一句話（「對」「不對」）推進，
不需要選項框。

## 台灣漢語口語用詞規範

Orchestrator 主對話以台灣漢語行文時，避免中國慣用口語詞，改用台灣漢語對應說法。

已點名的替換範例：

| 中國慣用詞 | 台灣漢語對應 |
|-----------|------------|
| 靠譜 | 可信 / 可靠 / 站得住腳 / 有把握 |

這條規範針對**日常口語選詞**，與 zh-TW UI glossary（管 UI 字串與命名）是不同層面，兩者各自獨立。遇到其他中國慣用詞，比照辦理，選最接近語意的台灣漢語說法替換。

**稱呼這個語言本身**：用「台灣漢語」或「華語」（英文 Taiwanese Mandarin），
盡量避免「繁體中文 / Traditional Chinese」——繁體是字形，不是語言。

## 與 narration 的分界

- 開場 / 收場 / 卡關的**旁白**（🌙 Doloris / 🌑 Mortis 的聲音、emoji prefix 規則）→
  [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)
- 對話本體的**互動與用詞**（何時用 widget、選詞規範）→ 本 skill
