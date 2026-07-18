#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка хода работ Codex по фильму «Пляж».

Читает PRODUCTION/LOGS/status.json и CODEX_JOURNAL.md, сверяет с требованиями
брифа и выводит отчёт: что сделано, что нарушено, на что смотреть.

Запуск:  python3 check_progress.py
"""

import json, os, re, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", ".."))
LOGS = os.path.join(PROJECT, "PRODUCTION", "LOGS")
STATUS = os.path.join(LOGS, "status.json")
JOURNAL = os.path.join(LOGS, "CODEX_JOURNAL.md")

STAGES = ["setup", "models", "keyframes", "faces", "upscale",
          "video", "voice", "music", "assembly", "qc"]

# требования из брифа: (путь в status.json, ожидание, текст нарушения)
RULES = [
    ("compliance.separate_face_passes", True,
     "Лица подставляются НЕ двумя раздельными проходами — Джон и Мэри смешаются"),
    ("compliance.explicit_content", False,
     "НАРУШЕНА политика контента: заявлен откровенный контент"),
    ("compliance.system_tts_used", False,
     "Используется системный TTS (macOS say) — именно от него уходим"),
    ("engines.voice_count", 4,
     "Голосов не 4 — роли перестанут различаться"),
]

BAR_W = 22


def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def bar(done, total):
    if not total:
        return "—" * BAR_W
    n = int(BAR_W * done / total)
    return "█" * n + "·" * (BAR_W - n)


def icon(status):
    return {"done": "✓", "in_progress": "▶", "blocked": "■",
            "failed": "✗", "pending": "·"}.get(status, "?")


def main():
    problems, warnings, notes = [], [], []

    if not os.path.exists(STATUS):
        print("status.json не найден:", STATUS)
        print("Codex ещё не начал работу либо не ведёт журнал по правилам.")
        print("См. PRODUCTION/LOGS/CODEX_JOURNAL_RULES_RU.md")
        return 1

    st = json.load(open(STATUS, encoding="utf-8"))

    print("=" * 62)
    print("ПРОВЕРКА ХОДА РАБОТ — фильм «Пляж»")
    print("=" * 62)

    upd = st.get("updated_at", "?")
    print("Обновлено:      ", upd)
    print("Текущий этап:   ", st.get("current_stage", "?"))

    # свежесть журнала
    try:
        t = datetime.fromisoformat(upd)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - t).total_seconds() / 3600
        print("Давность записи: %.1f ч" % age_h)
        if age_h > 3:
            warnings.append("Журнал не обновлялся %.1f ч — работа могла встать" % age_h)
    except Exception:
        warnings.append("Не удалось разобрать updated_at — формат должен быть ISO")

    # --- этапы ---
    print("\nЭТАПЫ")
    print("-" * 62)
    stages = st.get("stages", {})
    for name in STAGES:
        s = stages.get(name, {})
        status = s.get("status", "pending")
        done, total = s.get("done"), s.get("total")
        line = "  %s %-10s %-12s" % (icon(status), name, status)
        if isinstance(done, int) and isinstance(total, int) and total:
            line += " %s %3d/%-3d" % (bar(done, total), done, total)
        if s.get("note"):
            line += "  " + str(s["note"])[:34]
        print(line)
        if status == "failed":
            problems.append("Этап '%s' провален: %s" % (name, s.get("note", "без пояснения")))
        if status == "blocked":
            problems.append("Этап '%s' заблокирован: %s" % (name, s.get("note", "без пояснения")))

    # --- движки ---
    print("\nДВИЖКИ")
    print("-" * 62)
    for k, v in (st.get("engines") or {}).items():
        print("  %-16s %s" % (k, v))

    # --- соответствие брифу ---
    print("\nСООТВЕТСТВИЕ БРИФУ")
    print("-" * 62)
    for path, expect, msg in RULES:
        val = get(st, path)
        ok = (val == expect)
        print("  %s %-34s = %-8s (нужно %s)" %
              ("✓" if ok else "✗", path.split(".")[-1], val, expect))
        if val is None:
            warnings.append("Поле %s не заполнено" % path)
        elif not ok:
            problems.append(msg)

    fb = get(st, "compliance.static_fallback_shots")
    if isinstance(fb, int):
        ok = fb <= 6
        print("  %s %-34s = %-8s (допустимо ≤6)" %
              ("✓" if ok else "✗", "static_fallback_shots", fb))
        if not ok:
            problems.append("Статичных планов %d — фильм скатывается обратно в motion-comic" % fb)

    # --- выход ---
    print("\nРЕЗУЛЬТАТ")
    print("-" * 62)
    out = st.get("output") or {}
    dur = out.get("duration_sec")
    print("  Длительность:   %s c%s" %
          (dur if dur else "—", "  (%d:%02d)" % (dur // 60, dur % 60) if dur else ""))
    print("  Разрешение:     %s" % (out.get("resolution") or "—"))
    print("  Кадров/с:       %s" % (out.get("fps") or "—"))
    print("  Мастер:         %s" % (out.get("master_path") or "—"))

    if dur is not None:
        if dur < 300:
            problems.append("Хронометраж %.0f c — меньше требуемых 5 минут (300 c)" % dur)
        else:
            notes.append("Хронометраж в норме: %d:%02d" % (dur // 60, dur % 60))
    if out.get("fps") not in (None, 24, "24"):
        problems.append("Частота кадров %s вместо 24" % out.get("fps"))

    # --- блокеры и отклонения ---
    for b in st.get("blockers") or []:
        problems.append("Блокер: %s" % b)
    devs = st.get("deviations") or []
    if devs:
        print("\nОТКЛОНЕНИЯ ОТ БРИФА (заявленные)")
        print("-" * 62)
        for d in devs:
            print("  •", d)
            notes.append("Отклонение заявлено: %s" % str(d)[:70])

    # --- журнал ---
    print("\nЖУРНАЛ")
    print("-" * 62)
    if not os.path.exists(JOURNAL):
        problems.append("CODEX_JOURNAL.md отсутствует — журнал не ведётся")
        print("  файл отсутствует")
    else:
        text = open(JOURNAL, encoding="utf-8").read()
        entries = re.findall(r"^##\s+(.+)$", text, re.M)
        probs_mentioned = len(re.findall(r"\*\*Проблемы:\*\*\s*(?!нет|—|-)\S", text))
        print("  Записей:        %d" % len(entries))
        print("  Размер:         %.1f КБ" % (len(text.encode()) / 1024))
        print("  С проблемами:   %d" % probs_mentioned)
        if entries:
            print("  Последняя:      %s" % entries[-1][:52])
        if len(entries) < 3 and st.get("current_stage") not in ("setup", None):
            warnings.append("Всего %d записей при работе не на старте — журнал ведётся формально"
                            % len(entries))
        if probs_mentioned == 0 and len(entries) >= 4:
            warnings.append("Ни одной зафиксированной проблемы за %d записей — "
                            "маловероятно, журнал может быть недостоверным" % len(entries))

    # --- итог ---
    print("\n" + "=" * 62)
    if problems:
        print("ТРЕБУЕТ ВМЕШАТЕЛЬСТВА (%d)" % len(problems))
        for p in problems:
            print("  ✗", p)
    if warnings:
        print("\nОБРАТИТЬ ВНИМАНИЕ (%d)" % len(warnings))
        for w in warnings:
            print("  !", w)
    if notes:
        print("\nВ порядке (%d)" % len(notes))
        for n in notes:
            print("  ✓", n)
    if not problems and not warnings:
        print("Замечаний нет — работа идёт по брифу.")
    print("=" * 62)

    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
