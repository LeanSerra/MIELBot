from difflib import get_close_matches
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from telegram import Update
from telegram.ext import ContextTypes, CallbackContext, Application
from bs4 import BeautifulSoup
from pandas import DataFrame
import re


def create_df_from_html_table(html: str, columns: list[str]) -> DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.table

    table_rows = table.find_all("tr")

    res = []
    for tr in table_rows:
        td = tr.find_all("td")
        row = [tr.text for tr in td if tr]
        if row:
            res.append(row)

    df: DataFrame = DataFrame(res, columns=columns)
    return df


def write_file(fileName: str, status: dict[int, dict]):
    with open(fileName, "w") as f:
        for key in status.keys():
            s = status[key]
            f.write(f"{key},{s['contenido']},{s['mensajeria']},{s['forov2']}\n")


def get_close_match_row_idx(materia: str, df: DataFrame, row_name: str) -> int:
    index = df.index[df[row_name] == materia]
    if len(index) > 0:
        return index[0]
    else:
        close_matches: list[str] = get_close_matches(
            materia, df[row_name], cutoff=0.8, n=1
        )
        if len(close_matches) == 1:
            return df.index[df[row_name] == close_matches[0]][0]
        else:
            return -1


def clean_materia(materia: str) -> str:
    materia = materia.lower()
    materia = re.sub(r"[àáâãäå]", "a", materia)
    materia = re.sub(r"[èéêë]", "e", materia)
    materia = re.sub(r"[ìíîï]", "i", materia)
    materia = re.sub(r"[òóôõö]", "o", materia)
    materia = re.sub(r"[ùúûü]", "u", materia)
    materia = materia.replace("1", "i")
    materia = materia.replace("2", "ii")
    materia = materia.replace("3", "iii")
    materia = materia.replace("4", "iv")
    materia = materia.replace("5", "v")
    materia = materia.replace("6", "vi")
    materia = materia.replace("7", "vii")
    materia = materia.replace("8", "viii")
    materia = materia.replace("9", "ix")
    materia = materia.replace("10", "x")
    return materia.upper()


async def oferta(
    update: Update, context: ContextTypes.DEFAULT_TYPE, html: str, chat_id: int
):
    if len(context.args) > 0:
        materia = " ".join(context.args)
        materia = clean_materia(materia)
    else:
        await context.bot.send_message(
            chat_id=chat_id, text="El comando debe ser: /oferta <nombre-materia>"
        )
        return

    df: DataFrame = create_df_from_html_table(
        html,
        [
            "Código",
            "Descripción",
            "Cod. Comisión",
            "Turno",
            "Días",
            "Modalidad",
            "Sede",
            "Observacion",
        ],
    )

    df["Código"] = df["Código"].apply(lambda s: int(s) if s.isdigit() else 0)

    num_rows: int = df.shape[0]

    idx: int = get_close_match_row_idx(materia, df, "Descripción")

    if idx == -1:
        await context.bot.send_message(
            chat_id=chat_id, text="No se encontro la materia"
        )
        return

    code: int = int(df.iloc[idx]["Código"])

    msg_data = f"""Codigo: {code}\n{df.iloc[idx]["Descripción"]}\nHorarios:\n"""

    for i in range(idx, num_rows):
        row = df.iloc[i]
        cod: str = row["Código"]
        if cod != 0 and cod != code:
            break

        if row["Cod. Comisión"] == "No Ofertada":
            msg_data = msg_data + "No Ofertada"
            break

        msg_data = (
            msg_data
            + f"""{"Mañana" if row["Turno"] == "M" else "Tarde" if row["Turno"] == "T" else "Noche"}\t{row["Días"]}\n"""
        )

    await context.bot.send_message(chat_id=chat_id, text=msg_data)


async def notas(
    update: Update, context: ContextTypes.DEFAULT_TYPE, html: str, chat_id: int
):
    n: int = 5

    df: DataFrame = create_df_from_html_table(
        html,
        [
            "Código",
            "Materia",
            "Fecha",
            "Nota",
            "Acta",
        ],
    )

    df["Código"] = df["Código"].apply(lambda s: int(s) if s.isdigit() else 0)
    df["Materia"] = df["Materia"].apply(lambda s: s.strip())

    num_rows: int = df.shape[0]

    if len(context.args) > 0:
        if context.args[0].isdigit():
            n = int(context.args[0])
        else:
            materia: str = clean_materia(" ".join(context.args))

            idx: int = get_close_match_row_idx(materia, df, "Materia")

            if idx == -1:
                await context.bot.send_message(
                    chat_id=chat_id, text="No se encontro la materia"
                )
                return

            row = df.iloc[idx]

            await context.bot.send_message(
                chat_id=chat_id, text=f"""{row["Materia"].strip()}\t{row["Nota"]}\n"""
            )

            return

    msg_data: str = f"""Ultimas {n} notas:\n"""

    for i in range(num_rows - n, num_rows):
        row = df.iloc[i]
        msg_data = msg_data + f"""{row["Materia"].strip()}\t{row["Nota"]}\n"""

    await context.bot.send_message(chat_id=chat_id, text=msg_data)


async def send_notification_miel(
    notifType: str, materia: str, chatId: int, application: Application
):
    await application.bot.send_message(chat_id=chatId, text=f"{materia}: {notifType}")


async def poll_miel(context: CallbackContext):
    print("Polling")

    driver: webdriver.Firefox = context.job.data["driver"]
    status: dict[int, dict[str, int]] = context.job.data["status"]
    application: Application = context.job.data["application"]
    chatId: int = context.job.data["chatId"]

    driver.refresh()

    for materiaDiv in driver.find_elements(By.CSS_SELECTOR, "div.w3-light-grey"):
        name: str = materiaDiv.find_element(By.CSS_SELECTOR, ".materia-titulo").text

        id: str | None = materiaDiv.get_attribute("data-id")
        idInt: int = 0
        if id is not None:
            idInt = int(id)

        contenidosCount = 0
        mensajeriaCount = 0
        foroCount = 0

        categories = materiaDiv.find_elements(
            By.CSS_SELECTOR, ".materia-herramientas>div>a"
        )

        if len(categories) < 4:
            continue
        for i in [0, 2, 3]:
            try:
                badge = categories[i].find_element(By.CSS_SELECTOR, "span")
            except NoSuchElementException:
                continue
            if badge is not None:
                count: int = int(badge.text)
                if i == 0:
                    contenidosCount = count
                elif i == 2:
                    mensajeriaCount = count
                elif i == 3:
                    foroCount = count

        if status[idInt]["contenido"] < contenidosCount:
            await send_notification_miel(
                notifType="contenido",
                materia=name,
                chatId=chatId,
                application=application,
            )
        status[idInt]["contenido"] = contenidosCount

        if status[idInt]["mensajeria"] < mensajeriaCount:
            await send_notification_miel(
                notifType="mensajeria",
                materia=name,
                chatId=chatId,
                application=application,
            )
        status[idInt]["mensajeria"] = mensajeriaCount

        if status[idInt]["forov2"] < foroCount:
            await send_notification_miel(
                notifType="foro",
                materia=name,
                chatId=chatId,
                application=application,
            )
        status[idInt]["forov2"] = foroCount
        write_file(".status", status)
