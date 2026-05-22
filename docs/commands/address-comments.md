```mermaid
flowchart TD
    Start([使用者: /maigo:address-comments]) --> Gate{當前 branch<br/>讀得到 PR?}
    Gate -- 否 --> Block([擋下: 印錯誤<br/>non-zero exit])
    Gate -- 是 --> Fetch[Orchestrator<br/>抓 inline / review / conversation 意見]
    Fetch --> HasComments{有意見?}
    HasComments -- 沒有 --> NoOp([結束: 無意見可處理])
    HasComments -- 有 --> List[Orchestrator 列出<br/>使用者挑哪些要處理]
    List --> Plan[Orchestrator 寫 pr-comments.md<br/>分組 work item + 提路由計畫]
    Plan --> Confirm{使用者確認<br/>分組 + 路由?}
    Confirm -- 要調整 --> Plan
    Confirm -- OK --> Route[逐 work item 跑指定 route]
    Route --> Fix[/maigo:fix]
    Route --> Go[/maigo:go]
    Route --> Team[/maigo:team]
    Fix --> Finale[Orchestrator finale<br/>處理對照 + 回覆草稿 + commit msg]
    Go --> Finale
    Team --> Finale
    Finale --> Done([完成])

    classDef gate fill:#FFC857,stroke:#333,color:#000
    classDef block fill:#FF6F91,stroke:#333,color:#000
    class Gate gate
    class Block block
```

{% include-markdown "../../commands/address-comments.md" start="<!-- mkdocs-include-start -->" %}
