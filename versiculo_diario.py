"""Versículo bíblico diário: Telegram (canal) + payload para o WhatsApp.

Escolhe o versículo do dia a partir de dados/versiculos_iasd_ara_5anos.json:
    índice = (dias desde VERSICULOS_DATA_INICIO, no fuso de Lisboa) mod N
Sem estado entre execuções: re-execuções no mesmo dia publicam o mesmo
versículo e o ciclo recomeça sozinho ao fim de N dias.

Modos:
    (normal)        publica no canal Telegram e escreve whatsapp_msg.txt,
                    consumido a seguir pelo send_whatsapp.js.
    --admin-teste   antes do lançamento: envia o versículo só para o chat
                    pessoal do administrador (TELEGRAM_PERSONAL_CHAT_ID), sem
                    tocar no payload do WhatsApp. Depois do lançamento não faz nada.
    --fase          imprime "teste" (antes do lançamento) ou "lancado".
    --dry-run       mostra as mensagens sem enviar.

Uso local:
    python versiculo_diario.py --dry-run [--data AAAA-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

FICHEIRO_VERSICULOS = Path(__file__).with_name("dados") / "versiculos_iasd_ara_5anos.json"
FICHEIRO_WHATSAPP = Path("whatsapp_msg.txt")
# Imagem para partilha (Facebook/Instagram); o send_whatsapp.js envia-a
# quando WHATSAPP_IMAGEM aponta para este ficheiro.
FICHEIRO_IMAGEM = Path("versiculo_do_dia.jpg")
FUSO = ZoneInfo("Europe/Lisbon")
# Lançamento oficial: dia em que é publicado o 1.º versículo (id 1). Antes
# desta data o bot está em teste (só chat do administrador). Pode ser
# alterado com a variável do repositório VERSICULOS_DATA_INICIO (AAAA-MM-DD).
DATA_INICIO_PADRAO = datetime.date(2027, 1, 1)
MAX_TENTATIVAS = 3
ESPERA_ENTRE_TENTATIVAS_S = 20

DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
_MDV2_ESPECIAIS = r"_*[]()~`>#+-=|{}.!\\"


def escapar_mdv2(texto: str) -> str:
    """Escapa texto para o parse_mode MarkdownV2 do Telegram."""
    return "".join("\\" + c if c in _MDV2_ESPECIAIS else c for c in texto)


def carregar_versiculos(caminho: Path) -> list[dict[str, str]]:
    """Lê o JSON e devolve a lista normalizada, ordenada pelo número do dia.

    Aceita o ficheiro completo ({"versiculos": [{id, referencia, texto, tema}]})
    e o formato da amostra ({"dias": [{dia, referencia, versiculo, crenca,
    aplicacao_pratica}]}). Falha com ValueError se algum registo estiver vazio.
    """
    with caminho.open(encoding="utf-8") as f:
        dados = json.load(f)

    if "versiculos" in dados:
        brutos = sorted(dados["versiculos"], key=lambda v: int(v["id"]))
        lista = [{
            "referencia": v.get("referencia", ""),
            "texto": v.get("texto", ""),
            "tema": v.get("tema", ""),
            "aplicacao": "",
        } for v in brutos]
    elif "dias" in dados:
        brutos = sorted(dados["dias"], key=lambda v: int(v["dia"]))
        lista = [{
            "referencia": v.get("referencia", ""),
            "texto": v.get("versiculo", ""),
            "tema": v.get("crenca", ""),
            "aplicacao": v.get("aplicacao_pratica", ""),
        } for v in brutos]
    else:
        raise ValueError("JSON sem a chave 'versiculos' nem 'dias'.")

    if not lista:
        raise ValueError("Lista de versículos vazia.")
    for i, v in enumerate(lista, start=1):
        v = {k: " ".join(str(s).split()) for k, s in v.items()}  # normaliza espaços
        lista[i - 1] = v
        if not v["referencia"] or not v["texto"]:
            raise ValueError(f"Registo n.º {i} sem referência ou texto.")
    return lista


def indice_do_dia(hoje: datetime.date, inicio: datetime.date, total: int) -> int:
    """Índice (0-based) do versículo de 'hoje'.

    Antes do início (fase de teste) continua a rodar, com os últimos
    versículos do ciclo, e cai exatamente no 1.º no dia do lançamento.
    """
    return (hoje - inicio).days % total


def _data_pt(d: datetime.date) -> str:
    return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]}"


def _hashtag(tema: str) -> str:
    return "#" + "_".join(tema.split()) if tema else ""


def formatar_telegram(v: dict[str, str], hoje: datetime.date) -> str:
    linhas = [
        f"📖 *Versículo do dia* — _{escapar_mdv2(_data_pt(hoje))}_",
        "",
        f"*{escapar_mdv2(v['referencia'])} \\(ARA\\)*",
        f"“{escapar_mdv2(v['texto'])}”",
    ]
    if v["aplicacao"]:
        linhas += ["", "💡 " + escapar_mdv2(v["aplicacao"])]
    if v["tema"]:
        linhas += ["", "🏷️ " + escapar_mdv2(_hashtag(v["tema"]))]
    return "\n".join(linhas)


def formatar_whatsapp(v: dict[str, str], hoje: datetime.date) -> str:
    linhas = [
        f"📖 *Versículo do dia* — _{_data_pt(hoje)}_",
        "",
        f"*{v['referencia']} (ARA)*",
        f"“{v['texto']}”",
    ]
    if v["aplicacao"]:
        linhas += ["", "💡 " + v["aplicacao"]]
    if v["tema"]:
        linhas += ["", "🏷️ " + _hashtag(v["tema"])]
    return "\n".join(linhas)


def _data_inicio() -> datetime.date:
    valor = (os.getenv("VERSICULOS_DATA_INICIO") or "").strip()
    if not valor:
        return DATA_INICIO_PADRAO
    try:
        return datetime.date.fromisoformat(valor)
    except ValueError:
        print(f"AVISO: VERSICULOS_DATA_INICIO inválida ({valor!r}); a usar {DATA_INICIO_PADRAO}.")
        return DATA_INICIO_PADRAO


def gerar_imagem_do_dia(v: dict[str, str], destino: Path = FICHEIRO_IMAGEM) -> Path | None:
    """Gera a imagem de partilha. Devolve None (e regista o erro) se falhar."""
    try:
        from imagem_versiculo import gerar_imagem
        caminho = gerar_imagem(v["referencia"], v["texto"], destino)
        print(f"Imagem gerada: {caminho} ({caminho.stat().st_size // 1024} KB).")
        return caminho
    except (ImportError, OSError, ValueError) as e:
        print(f"ERRO ao gerar a imagem: {type(e).__name__}: {e}")
        destino.unlink(missing_ok=True)  # nunca deixar uma imagem antiga para o WhatsApp
        return None


def enviar_foto_telegram(token: str, chat_id: str, caminho: Path) -> tuple[bool, str]:
    """sendPhoto sem legenda (sem hashtags). O erro nunca contém o token."""
    import requests  # import tardio, como o resto do envio

    erro = ""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            with caminho.open("rb") as f:
                r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                                  data={"chat_id": chat_id},
                                  files={"photo": (caminho.name, f, "image/jpeg")},
                                  timeout=30)
            r.raise_for_status()
            print("Imagem enviada para o Telegram.")
            return True, ""
        except (requests.exceptions.RequestException, OSError) as e:
            erro = str(e)
            resposta = getattr(e, "response", None)
            if resposta is not None:
                erro += " | " + resposta.text[:300]
            erro = erro.replace(token, "***")
            print(f"Falha no envio da imagem (tentativa {tentativa}/{MAX_TENTATIVAS}): {erro}")
            if tentativa < MAX_TENTATIVAS:
                time.sleep(ESPERA_ENTRE_TENTATIVAS_S)
    return False, erro


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="mostra as mensagens sem enviar")
    parser.add_argument("--data", type=datetime.date.fromisoformat,
                        help="simula outro dia (AAAA-MM-DD)")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--admin-teste", action="store_true",
                      help="antes do lançamento: envia só para o chat do administrador")
    modo.add_argument("--fase", action="store_true",
                      help='imprime "teste" ou "lancado" e sai')
    args = parser.parse_args(argv)

    hoje = args.data or datetime.datetime.now(FUSO).date()
    inicio = _data_inicio()
    em_teste = hoje < inicio

    if args.fase:
        print("teste" if em_teste else "lancado")
        return 0
    if args.admin_teste and not em_teste:
        print(f"Lançamento em {inicio} já ocorreu: modo de teste inativo.")
        return 0

    # Import tardio: o módulo das meditações traz requests/bs4, desnecessários
    # para --dry-run e para os testes das funções puras acima.
    if not args.dry_run:
        from meditacao_iasdah import send_admin_alert, send_telegram_message

    try:
        versiculos = carregar_versiculos(FICHEIRO_VERSICULOS)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"ERRO: não foi possível carregar {FICHEIRO_VERSICULOS}: {e}")
        if not args.dry_run:
            send_admin_alert("Falha no bot do versículo diário",
                             f"Não foi possível carregar o ficheiro de versículos: {e}")
        return 1

    i = indice_do_dia(hoje, inicio, len(versiculos))
    v = versiculos[i]
    msg_tg = formatar_telegram(v, hoje)
    msg_wa = formatar_whatsapp(v, hoje)
    print(f"Data (Lisboa): {hoje} | início: {inicio} | versículo {i + 1}/{len(versiculos)}: {v['referencia']}")

    if args.admin_teste:
        cabecalho = escapar_mdv2(f"🧪 TESTE — só para o administrador. "
                                 f"Lançamento a {inicio:%d-%m-%Y} "
                                 f"(versículo {i + 1}/{len(versiculos)}).")
        msg_tg = cabecalho + "\n\n" + msg_tg

    if args.dry_run:
        print("\n--- Telegram (MarkdownV2) ---\n" + msg_tg)
        if not args.admin_teste:
            print("\n--- WhatsApp ---\n" + msg_wa)
        gerar_imagem_do_dia(v)
        return 0

    if args.admin_teste:
        # Só Telegram pessoal; o whatsapp_msg.txt das meditações fica intacto.
        # A imagem vai para um nome próprio para nunca chegar ao WhatsApp.
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_admin = os.getenv("TELEGRAM_PERSONAL_CHAT_ID")
        if not token or not chat_admin:
            print("ERRO: TELEGRAM_BOT_TOKEN ou TELEGRAM_PERSONAL_CHAT_ID não definidos.")
            return 1
        ok, erro = send_telegram_message(msg_tg, token, chat_admin)
        if not ok:
            print("Falha no envio de teste: " + (erro or "").replace(token, "***"))
        imagem = gerar_imagem_do_dia(v, Path("versiculo_teste.jpg"))
        ok_img = bool(imagem) and enviar_foto_telegram(token, chat_admin, imagem)[0]
        return 0 if ok and ok_img else 1

    # Payload do WhatsApp e imagem primeiro: uma falha no Telegram não deve
    # impedir o grupo.
    FICHEIRO_WHATSAPP.write_text(msg_wa + "\n", encoding="utf-8")
    print(f"Payload do WhatsApp escrito em {FICHEIRO_WHATSAPP}.")
    imagem = gerar_imagem_do_dia(v)
    falhas: list[str] = []
    if not imagem:
        falhas.append("A imagem de partilha não foi gerada (ver logs).")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("ERRO: TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não definidos.")
        send_admin_alert("Falha no bot do versículo diário",
                         "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não definidos; o Telegram não foi publicado.")
        return 0  # o WhatsApp ainda corre

    texto_ok, ultimo_erro = False, ""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        texto_ok, erro = send_telegram_message(msg_tg, token, chat_id)
        if texto_ok:
            break
        # O erro do requests inclui o URL, que contém o token do bot.
        ultimo_erro = (erro or "").replace(token, "***")
        print(f"Falha no envio Telegram (tentativa {tentativa}/{MAX_TENTATIVAS}): {ultimo_erro}")
        if tentativa < MAX_TENTATIVAS:
            time.sleep(ESPERA_ENTRE_TENTATIVAS_S)
    if not texto_ok:
        falhas.append(f"Envio de {v['referencia']} para o canal Telegram falhou: {ultimo_erro}")

    if imagem:
        ok_img, erro_img = enviar_foto_telegram(token, chat_id, imagem)
        if not ok_img:
            falhas.append(f"Envio da imagem para o canal Telegram falhou: {erro_img}")

    if falhas:
        send_admin_alert("Falha no bot do versículo diário", "\n".join(falhas))
    return 0  # alertas já enviados; o WhatsApp ainda corre


if __name__ == "__main__":
    sys.exit(main())
