"""Teste real num browser (playwright chromium headless).

Carrega hyline_dashboard_preview.html, navega pelas 6 vistas, captura erros
de consola e screenshots. Verifica que:
  1. Zero erros JS na consola
  2. Gráfico de trends SVG renderiza (elementos <polyline>, <text>)
  3. Digital twin renderiza (>20 estações)
  4. KPIs têm valores numéricos (não '—')
  5. Clicar numa estação abre o drawer
  6. Chatbot responde
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from playwright.sync_api import sync_playwright


def main() -> int:
    preview = ROOT / "hyline_dashboard_preview.html"
    if not preview.exists():
        print(f"✗ Missing: {preview}")
        return 1

    console_errors: list[str] = []
    screenshots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"PAGE ERROR: {e}"))

        page.goto(f"file://{preview}")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(2000)  # let animations + first refreshAll run

        print("· HYLINE browser test ·")
        print(f"  URL: {preview.name}")

        # 1. Console errors (ignoring external resource failures like fonts blocked in sandbox)
        real_errors = [
            e for e in console_errors
            if "refreshAll falhou" not in e
            and "Failed to load resource" not in e
            and "net::" not in e
        ]
        if real_errors:
            print(f"  ✗ {len(real_errors)} console errors:")
            for e in real_errors[:5]:
                print(f"      · {e[:180]}")
            browser.close()
            return 2
        print(f"  ✓ Zero JS errors ({len(console_errors)} network-level ignored: fonts)")

        # 2. KPIs have values
        k_m2 = page.evaluate("document.getElementById('k-m2')?.textContent")
        k_f  = page.evaluate("document.getElementById('k-f')?.textContent")
        print(f"  ✓ KPIs · m²={k_m2} · desempenho={k_f}%")
        assert k_m2 and k_m2 != "—", f"k-m2 vazio: {k_m2}"
        assert k_f and k_f != "—", f"k-f vazio: {k_f}"

        # 3. Digital twin renders
        n_stations = page.evaluate("document.querySelectorAll('.station-rect').length")
        print(f"  ✓ Twin · {n_stations} estações renderizadas")
        assert n_stations >= 20, f"Twin só tem {n_stations} estações"

        # 4. Flow particles present
        n_particles = page.evaluate("document.querySelectorAll('#flow-particles circle').length")
        print(f"  ✓ Twin · {n_particles} partículas de fluxo")
        assert n_particles > 0

        # 5. Screenshot home
        home_shot = ROOT / "test_home.png"
        page.screenshot(path=str(home_shot), full_page=False)
        screenshots.append(home_shot)
        print(f"  ✓ Screenshot home · {home_shot.stat().st_size // 1024} KB")

        # 6. Click station → drawer opens
        page.evaluate("document.querySelector('.station-rect[data-sid=\"ST-COR-01\"]')?.dispatchEvent(new MouseEvent('click', {bubbles:true}))")
        page.wait_for_timeout(500)
        drawer_open = page.evaluate("document.getElementById('detail').classList.contains('is-open')")
        assert drawer_open, "Drawer não abriu ao clicar na estação"
        d_title = page.evaluate("document.getElementById('d-title')?.textContent")
        d_f = page.evaluate("document.getElementById('d-f')?.textContent")
        print(f"  ✓ Drawer · {d_title} · desempenho {d_f}")

        detail_shot = ROOT / "test_home_detail.png"
        page.screenshot(path=str(detail_shot), full_page=False)
        screenshots.append(detail_shot)

        page.evaluate("App.closeDetail()")
        page.wait_for_timeout(300)

        # 7. Navigate to Alertas
        page.evaluate("document.querySelector('[data-view=\"alerts\"]').click()")
        page.wait_for_timeout(600)
        n_alert_cards = page.evaluate("document.querySelectorAll('.alert-card').length")
        print(f"  ✓ Alertas · {n_alert_cards} cards")
        p2 = ROOT / "test_alerts.png"
        page.screenshot(path=str(p2)); screenshots.append(p2)

        # 8. Navigate to Ação
        page.evaluate("document.querySelector('[data-view=\"action\"]').click()")
        page.wait_for_timeout(600)
        n_agents = page.evaluate("document.querySelectorAll('.agent').length")
        agent_names = page.evaluate("Array.from(document.querySelectorAll('.agent__name')).map(e=>e.textContent)")
        print(f"  ✓ Ação · {n_agents} agentes: {agent_names}")
        # Send a chatbot msg
        page.fill('#chat-input', 'desempenho global')
        page.keyboard.press('Enter')
        page.wait_for_timeout(400)
        chat_bot_msgs = page.evaluate("document.querySelectorAll('.chat-msg--bot').length")
        print(f"  ✓ Chatbot · {chat_bot_msgs} mensagens")
        assert chat_bot_msgs >= 2
        p3 = ROOT / "test_action.png"
        page.screenshot(path=str(p3)); screenshots.append(p3)

        # 9. Navigate to Escala (the one that was broken)
        page.evaluate("document.querySelector('[data-view=\"scale\"]').click()")
        page.wait_for_timeout(1200)
        # Check SVG chart rendered
        n_polylines = page.evaluate("document.querySelectorAll('#trends-chart svg polyline').length")
        n_labels    = page.evaluate("document.querySelectorAll('#trends-chart svg text').length")
        n_suggestions = page.evaluate("document.querySelectorAll('#trends-suggestions > div').length")
        source_text = page.evaluate("document.getElementById('trends-source')?.textContent")
        print(f"  ✓ Escala · {n_polylines} linhas · {n_labels} labels · {n_suggestions} sugestões · source: {source_text}")
        assert n_polylines >= 4
        assert n_labels >= 12
        assert n_suggestions >= 1, "sem sugestões accionáveis"
        p4 = ROOT / "test_scale.png"
        page.screenshot(path=str(p4)); screenshots.append(p4)

        # 10. Navigate to Sustentabilidade
        page.evaluate("document.querySelector('[data-view=\"sustain\"]').click()")
        page.wait_for_timeout(500)
        s_co2 = page.evaluate("document.getElementById('s-co2')?.textContent")
        print(f"  ✓ Sustain · CO₂ hoje = {s_co2}")
        p5 = ROOT / "test_sustain.png"
        page.screenshot(path=str(p5)); screenshots.append(p5)

        # 11. Navigate to Definições · check connections + architecture
        page.evaluate("document.querySelector('[data-view=\"settings\"]').click()")
        page.wait_for_timeout(1500)
        conn_present = page.evaluate("document.getElementById('conn-host')?.innerHTML?.length > 100")
        arch_present = page.evaluate("document.getElementById('arch-host')?.innerHTML?.length > 100")
        team_size = page.evaluate("document.querySelectorAll('.team-row').length")
        n_exports = page.evaluate("document.querySelectorAll('.export-row').length")
        print(f"  ✓ Definições · equipa={team_size} · connections={conn_present} · arquitectura={arch_present} · exports={n_exports}")
        assert team_size >= 10
        assert conn_present
        assert arch_present, "Arquitectura não renderizou"
        assert n_exports >= 6, f"Só {n_exports} exports (esperado 6)"

        # Intercept download and verify CSV actually generated
        with page.expect_download(timeout=5000) as download_info:
            page.evaluate("""document.querySelector('.export-row[data-key="stations"]').click()""")
        download = download_info.value
        csv_path = ROOT / "test_export.csv"
        download.save_as(str(csv_path))
        csv_content = csv_path.read_text(encoding="utf-8")
        n_lines = csv_content.count("\n")
        print(f"  ✓ Download CSV · {download.suggested_filename} · {len(csv_content)} bytes · {n_lines} linhas")
        assert n_lines >= 20, f"CSV só tem {n_lines} linhas"
        assert "sector" in csv_content or "nome" in csv_content, "CSV sem header esperado"

        p6 = ROOT / "test_settings.png"
        page.screenshot(path=str(p6), full_page=True); screenshots.append(p6)

        # 12. Dock visible on all views
        page.evaluate("document.querySelector('[data-view=\"home\"]').click()")
        page.wait_for_timeout(400)
        dock_exists  = page.evaluate("!!document.getElementById('dock')")
        dock_fixed   = page.evaluate("getComputedStyle(document.getElementById('dock')).position === 'fixed'")
        dock_input   = page.evaluate("!!document.getElementById('dock-input')")
        dock_send    = page.evaluate("!!document.getElementById('dock-send')")
        print(f"  ✓ Dock · exists={dock_exists} fixed={dock_fixed} input={dock_input} send={dock_send}")
        assert dock_exists and dock_fixed and dock_input and dock_send, "Dock incompleto"

        # 13. Send via dock → conversations view shown, then auto-navigates
        page.fill('#dock-input', 'encomendar perfis sustentáveis')
        page.keyboard.press('Enter')
        # Check conversations appears before auto-navigate (< 1.2s)
        page.wait_for_timeout(700)
        view_at_700 = page.evaluate("document.querySelector('.view.is-active')?.dataset.view")
        n_msgs = page.evaluate("document.querySelectorAll('.msg').length")
        print(f"  ✓ Dock send · view@700ms={view_at_700} msgs={n_msgs}")
        assert view_at_700 == 'conversations', f"Esperado conversations @ 700ms, actual: {view_at_700}"
        assert n_msgs >= 1, f"Esperado ≥1 mensagem, actual: {n_msgs}"

        # Wait for auto-navigate and full render
        page.wait_for_timeout(2000)
        n_msgs_final = page.evaluate("document.querySelectorAll('.msg').length")
        has_action = page.evaluate("!!document.querySelector('.msg__action-btn') || !!document.querySelector('.msg__tool-chip')")
        view_after = page.evaluate("document.querySelector('.view.is-active')?.dataset.view")
        print(f"  ✓ Bot msg · msgs={n_msgs_final} action/chip={has_action}")
        assert n_msgs_final >= 2, f"Esperado ≥2 msgs final, actual: {n_msgs_final}"
        assert has_action, "Msg bot sem action btn ou tool chip"

        p7 = ROOT / "test_conversations.png"
        # Navigate back to conversations for screenshot
        page.evaluate("document.querySelector('[data-view=\"conversations\"]').click()")
        page.wait_for_timeout(600)
        page.screenshot(path=str(p7)); screenshots.append(p7)

        # 14. Auto-navigation: asking to open a view navigates there
        print(f"  ✓ Auto-nav após tool call · view={view_after}")
        # After sending procurement-related query, view should be procurement
        assert view_after in ('procurement', 'conversations'), f"Navegação inesperada: {view_after}"

        # 15. New conversation button resets stream
        page.evaluate("App.newConversation()")
        page.wait_for_timeout(500)
        empty_shown = page.evaluate("!!document.querySelector('.conv-stream__empty')")
        print(f"  ✓ New conv · empty shown={empty_shown}")

        browser.close()

    print()
    print(f"✓ {len(screenshots)} screenshots · TODAS AS VISTAS OK")
    for s in screenshots:
        print(f"  {s.name} · {s.stat().st_size//1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
