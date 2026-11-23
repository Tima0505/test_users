"""Тест-раннер Django, который после `python manage.py test` сохраняет результаты в Word.

Подключается в settings.py: TEST_RUNNER = 'users.report_runner.WordReportRunner'.
Результаты берутся из реального прогона: статус, время и текст ошибки каждого теста.
"""
import platform
import time
import unittest
from datetime import datetime

import django
from django.conf import settings
from django.test.runner import DiscoverRunner
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

GROUPS = {
    'RegistrationTests': 'Регистрация',
    'LoginTests': 'Авторизация',
    'CaptchaTests': 'Капча',
    'ProfileTests': 'Личный кабинет',
}
COLORS = {'PASSED': RGBColor(0x1E, 0x8E, 0x3E), 'FAILED': RGBColor(0xC6, 0x28, 0x28),
          'ERROR': RGBColor(0xC6, 0x28, 0x28), 'SKIPPED': RGBColor(0x88, 0x88, 0x88)}


class RecordingResult(unittest.TextTestResult):
    """Обычный результат unittest, который дополнительно запоминает каждый тест."""

    records = []

    def startTest(self, test):
        self._started = time.perf_counter()
        super().startTest(test)

    def _record(self, test, status, details=''):
        RecordingResult.records.append({
            'group': GROUPS.get(type(test).__name__, type(test).__name__),
            'name': test._testMethodName,
            'doc': (test._testMethodDoc or '').strip().splitlines()[0] if test._testMethodDoc else '',
            'status': status,
            'time': time.perf_counter() - getattr(self, '_started', time.perf_counter()),
            'details': details,
        })

    def addSuccess(self, test):
        super().addSuccess(test); self._record(test, 'PASSED')

    def addFailure(self, test, err):
        super().addFailure(test, err); self._record(test, 'FAILED', self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err); self._record(test, 'ERROR', self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self._record(test, 'SKIPPED', reason)


def _shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd'); shd.set(qn('w:val'), 'clear'); shd.set(qn('w:fill'), color)
    tcPr.append(shd)


def write_report(records, path, duration):
    doc = Document()
    normal = doc.styles['Normal']
    normal.font.name = 'Arial'; normal.font.size = Pt(10.5)
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(1.8)

    total = len(records)
    passed = sum(r['status'] == 'PASSED' for r in records)
    failed = sum(r['status'] in ('FAILED', 'ERROR') for r in records)

    title = doc.add_paragraph(); title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run('Отчёт об автоматическом тестировании'); run.bold = True; run.font.size = Pt(16)
    sub = doc.add_paragraph(); sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run('Модуль users: регистрация, авторизация с капчей, личный кабинет').font.size = Pt(11.5)

    info = doc.add_paragraph()
    for label, value in [
        ('Дата запуска: ', datetime.now().strftime('%d.%m.%Y %H:%M')),
        ('Окружение: ', f'Python {platform.python_version()}, Django {django.get_version()}'),
        ('Команда: ', 'python manage.py test'),
        ('Время прогона: ', f'{duration:.2f} с'),
    ]:
        info.add_run(label).bold = True
        info.add_run(value + '\n')
    info.add_run('Итог: ').bold = True
    verdict = info.add_run(f'{passed} из {total} тестов пройдено' + ('' if not failed else f', упало: {failed}'))
    verdict.bold = True
    verdict.font.color.rgb = COLORS['PASSED'] if not failed else COLORS['FAILED']

    # Сводка по группам
    doc.add_paragraph().add_run('Сводка по разделам').bold = True
    groups = list(dict.fromkeys(r['group'] for r in records))
    summary = doc.add_table(rows=1, cols=4); summary.style = 'Table Grid'
    for i, h in enumerate(['Раздел', 'Тестов', 'Пройдено', 'Не пройдено']):
        cell = summary.rows[0].cells[i]; cell.text = h; _shade(cell, 'DCE6F0')
        cell.paragraphs[0].runs[0].bold = True
    for g in groups:
        rows = [r for r in records if r['group'] == g]
        ok = sum(r['status'] == 'PASSED' for r in rows)
        cells = summary.add_row().cells
        for i, v in enumerate([g, len(rows), ok, len(rows) - ok]):
            cells[i].text = str(v)

    # Подробная таблица
    doc.add_paragraph()
    doc.add_paragraph().add_run('Результаты по каждому тесту').bold = True
    table = doc.add_table(rows=1, cols=6); table.style = 'Table Grid'; table.alignment = WD_TABLE_ALIGNMENT.CENTER
    widths = [Cm(0.9), Cm(2.6), Cm(4.6), Cm(6.0), Cm(2.0), Cm(1.5)]
    for i, h in enumerate(['№', 'Раздел', 'Тест', 'Что проверяется', 'Результат', 'Время, с']):
        cell = table.rows[0].cells[i]; cell.text = h; _shade(cell, 'DCE6F0')
        cell.paragraphs[0].runs[0].bold = True
    for n, r in enumerate(records, 1):
        cells = table.add_row().cells
        values = [str(n), r['group'], r['name'], r['doc'], r['status'], f"{r['time']:.3f}"]
        for i, v in enumerate(values):
            cells[i].text = v
            for p in cells[i].paragraphs:
                for rn in p.runs:
                    rn.font.size = Pt(9)
        status_run = cells[4].paragraphs[0].runs[0]
        status_run.bold = True; status_run.font.color.rgb = COLORS[r['status']]
    for row in table.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = w

    problems = [r for r in records if r['status'] in ('FAILED', 'ERROR')]
    if problems:
        doc.add_paragraph()
        doc.add_paragraph().add_run('Подробности ошибок').bold = True
        for r in problems:
            p = doc.add_paragraph(); p.add_run(f"{r['group']}: {r['name']} ({r['status']})").bold = True
            tb = doc.add_paragraph(r['details'].strip()[-1500:])
            for rn in tb.runs:
                rn.font.name = 'Courier New'; rn.font.size = Pt(8)

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)


class WordReportRunner(DiscoverRunner):
    def get_resultclass(self):
        return RecordingResult

    def run_suite(self, suite, **kwargs):
        RecordingResult.records = []
        started = time.perf_counter()
        result = super().run_suite(suite, **kwargs)
        path = getattr(settings, 'TEST_REPORT_PATH')
        write_report(RecordingResult.records, path, time.perf_counter() - started)
        self.log(f'\nWord-отчёт сохранён: {path}')
        return result
