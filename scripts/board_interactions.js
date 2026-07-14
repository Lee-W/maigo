/* Work Board reading-layer filters and per-section sorting. */
(function () {
  "use strict";

  function initBoardControls() {
    const controls = document.querySelector(".work-controls");
    if (!controls || controls.dataset.initialized === "true") return;
    controls.dataset.initialized = "true";

    const search = document.querySelector("#board-search");
    const kind = document.querySelector("#board-kind");
    const status = document.querySelector("#board-status");
    const sort = document.querySelector("#board-sort");
    const reset = document.querySelector("#board-reset");
    const count = document.querySelector("#board-visible-count");
    const tables = [...document.querySelectorAll(".work-table")];
    const rows = tables.flatMap((table) => [...table.tBodies[0].rows]);

    async function copyCommand(button) {
      const command = button.dataset.copyCommand;
      try {
        await navigator.clipboard.writeText(command);
      } catch (_error) {
        const fallback = document.createElement("textarea");
        fallback.value = command;
        fallback.style.position = "fixed";
        fallback.style.opacity = "0";
        document.body.append(fallback);
        fallback.select();
        document.execCommand("copy");
        fallback.remove();
      }
      const original = button.textContent;
      button.textContent = "已複製";
      window.setTimeout(() => {
        button.textContent = original;
      }, 1200);
    }

    document.addEventListener("click", (event) => {
      const button = event.target.closest("[data-copy-command]");
      if (button) copyCommand(button);
    });

    [...new Set(rows.map((row) => row.dataset.status))]
      .sort((a, b) => a.localeCompare(b, "zh-Hant"))
      .forEach((value) => status.add(new Option(value, value)));

    function compareRows(left, right) {
      const mode = sort.value;
      if (mode === "author" || mode === "title") {
        return left.dataset[mode].localeCompare(right.dataset[mode], "zh-Hant");
      }
      if (mode.startsWith("changes")) {
        const leftChanges = Number(left.dataset.changes);
        const rightChanges = Number(right.dataset.changes);
        if (leftChanges < 0 && rightChanges >= 0) return 1;
        if (rightChanges < 0 && leftChanges >= 0) return -1;
        return mode === "changes-desc"
          ? rightChanges - leftChanges
          : leftChanges - rightChanges;
      }
      return Number(left.dataset.order) - Number(right.dataset.order);
    }

    function update() {
      const query = search.value.trim().toLocaleLowerCase("zh-Hant");
      let visible = 0;
      rows.forEach((row) => {
        const matches =
          (!query || row.dataset.search.includes(query)) &&
          (!kind.value || row.dataset.kind === kind.value) &&
          (!status.value || row.dataset.status === status.value);
        row.hidden = !matches;
        if (matches) visible += 1;
      });

      tables.forEach((table) => {
        const body = table.tBodies[0];
        [...body.rows].sort(compareRows).forEach((row) => body.append(row));
        table.closest(".work-table-wrap").hidden = ![...body.rows].some(
          (row) => !row.hidden,
        );
      });
      count.textContent = `顯示 ${visible} / ${rows.length}`;
    }

    [search, kind, status, sort].forEach((control) => {
      control.addEventListener(control === search ? "input" : "change", update);
    });
    reset.addEventListener("click", () => {
      search.value = "";
      kind.value = "";
      status.value = "";
      sort.value = "board";
      update();
      search.focus();
    });
    update();
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(initBoardControls);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initBoardControls);
  } else {
    initBoardControls();
  }
})();
