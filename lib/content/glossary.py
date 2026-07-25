"""Bilingual EN↔ES financial/crypto/Sapphire terminology.

Neutral Latin American Spanish — the audience is US-based Spanish speakers,
Houston in particular (44.2% Hispanic per the Sapphire OS charter). That
rules out Spain-specific forms (`vosotros`, `ordenador`, `cartera` for
wallet) and highly regional slang.

Every entry is a `Term` with:
  - `en`:       lowercased English form used as the dict key
  - `es`:       preferred Spanish rendering
  - `category`: one of CATEGORIES (used by the translator to prioritize
                consistency in a report kind's dominant vocabulary)
  - `plural_es` (optional): overrides simple "+s" plural where Spanish
                needs a different form (e.g. estrategia → estrategias is
                fine, but `pez` → `peces`). Empty by default.

The glossary is deliberately a plain module-level dict so tests can
introspect completeness without I/O, and so importing it stays free.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

CATEGORIES: tuple[str, ...] = (
    "trading",
    "crypto",
    "financial",
    "technical_analysis",
    "sapphire",
    "risk",
    "common",
)


@dataclass(frozen=True)
class Term:
    en: str
    es: str
    category: str
    plural_es: str = ""
    notes: str = field(default="", compare=False)


def _t(en: str, es: str, category: str, plural_es: str = "", notes: str = "") -> Term:
    return Term(en=en.lower(), es=es, category=category, plural_es=plural_es, notes=notes)


# ── Trading ───────────────────────────────────────────────────────────────────
_TRADING: tuple[Term, ...] = (
    _t("bull market", "mercado alcista", "trading"),
    _t("bear market", "mercado bajista", "trading"),
    _t("sideways market", "mercado lateral", "trading"),
    _t("volatility", "volatilidad", "trading"),
    _t("leverage", "apalancamiento", "trading"),
    _t("liquidity", "liquidez", "trading"),
    _t("liquidation", "liquidación", "trading"),
    _t("position", "posición", "trading"),
    _t("long", "posición larga", "trading", notes="preferred over just 'largo' for clarity"),
    _t("short", "posición corta", "trading"),
    _t(
        "stop loss",
        "stop de pérdidas",
        "trading",
        notes="'stop' is accepted loanword in LatAm trading",
    ),
    _t("take profit", "toma de ganancias", "trading"),
    _t("entry price", "precio de entrada", "trading"),
    _t("exit price", "precio de salida", "trading"),
    _t("target price", "precio objetivo", "trading"),
    _t("order", "orden", "trading"),
    _t("limit order", "orden limitada", "trading"),
    _t("market order", "orden de mercado", "trading"),
    _t("spread", "diferencial", "trading"),
    _t("slippage", "deslizamiento", "trading"),
    _t("volume", "volumen", "trading"),
    _t("open interest", "interés abierto", "trading"),
    _t("funding rate", "tasa de financiamiento", "trading"),
    _t("perpetual", "perpetuo", "trading"),
    _t("futures", "futuros", "trading"),
    _t("options", "opciones", "trading"),
    _t("margin", "margen", "trading"),
    _t("hedge", "cobertura", "trading"),
    _t("arbitrage", "arbitraje", "trading"),
    _t("scalp", "scalping", "trading", notes="loanword accepted"),
    _t("swing trade", "operación de swing", "trading"),
    _t("day trade", "operación intradía", "trading"),
    _t("trader", "operador", "trading"),
    _t("trade", "operación", "trading", plural_es="operaciones"),
    _t("trading pair", "par de operación", "trading"),
)

# ── Crypto ────────────────────────────────────────────────────────────────────
_CRYPTO: tuple[Term, ...] = (
    _t("wallet", "billetera", "crypto", notes="LatAm: billetera; Spain uses cartera"),
    _t("hot wallet", "billetera caliente", "crypto"),
    _t("cold wallet", "billetera fría", "crypto"),
    _t("hardware wallet", "billetera de hardware", "crypto"),
    _t("staking", "staking", "crypto", notes="loanword — no established Spanish translation"),
    _t("mining", "minería", "crypto"),
    _t("miner", "minero", "crypto"),
    _t("smart contract", "contrato inteligente", "crypto"),
    _t("blockchain", "cadena de bloques", "crypto"),
    _t("cryptocurrency", "criptomoneda", "crypto"),
    _t("crypto", "cripto", "crypto"),
    _t("token", "token", "crypto"),
    _t("stablecoin", "moneda estable", "crypto"),
    _t("gas fee", "tarifa de gas", "crypto"),
    _t("gas", "gas", "crypto"),
    _t("node", "nodo", "crypto"),
    _t("validator", "validador", "crypto"),
    _t("consensus", "consenso", "crypto"),
    _t("fork", "bifurcación", "crypto"),
    _t("airdrop", "airdrop", "crypto", notes="loanword"),
    _t("dex", "exchange descentralizado", "crypto"),
    _t("cex", "exchange centralizado", "crypto"),
    _t("liquidity pool", "pool de liquidez", "crypto"),
    _t("yield farming", "farmeo de rendimiento", "crypto"),
    _t("defi", "finanzas descentralizadas", "crypto"),
    _t("nft", "NFT", "crypto", notes="acronym kept"),
    _t("dao", "DAO", "crypto"),
    _t("private key", "clave privada", "crypto"),
    _t("public key", "clave pública", "crypto"),
    _t("seed phrase", "frase semilla", "crypto"),
    _t("bridge", "puente", "crypto"),
    _t("layer 2", "capa 2", "crypto"),
    _t("rollup", "rollup", "crypto"),
    _t("mainnet", "red principal", "crypto"),
    _t("testnet", "red de pruebas", "crypto"),
    _t("halving", "halving", "crypto"),
    _t("whale", "ballena", "crypto"),
    _t("rug pull", "estafa de salida", "crypto"),
    _t("on-chain", "en cadena", "crypto"),
    _t("off-chain", "fuera de cadena", "crypto"),
)

# ── Financial ─────────────────────────────────────────────────────────────────
_FINANCIAL: tuple[Term, ...] = (
    _t("portfolio", "cartera", "financial", notes="here cartera = portfolio, not wallet"),
    _t("yield", "rendimiento", "financial"),
    _t("return", "retorno", "financial"),
    _t("returns", "retornos", "financial"),
    _t("capital", "capital", "financial"),
    _t("asset", "activo", "financial", plural_es="activos"),
    _t("liability", "pasivo", "financial"),
    _t("equity", "patrimonio", "financial"),
    _t("debt", "deuda", "financial"),
    _t("interest", "interés", "financial"),
    _t("interest rate", "tasa de interés", "financial"),
    _t("inflation", "inflación", "financial"),
    _t("deflation", "deflación", "financial"),
    _t("dividend", "dividendo", "financial"),
    _t("stock", "acción", "financial", plural_es="acciones"),
    _t("bond", "bono", "financial"),
    _t("commodity", "materia prima", "financial", plural_es="materias primas"),
    _t("cash flow", "flujo de caja", "financial"),
    _t("balance sheet", "balance general", "financial"),
    _t("income statement", "estado de resultados", "financial"),
    _t("profit", "ganancia", "financial"),
    _t("loss", "pérdida", "financial", plural_es="pérdidas"),
    _t("revenue", "ingresos", "financial"),
    _t("valuation", "valoración", "financial"),
    _t("market cap", "capitalización de mercado", "financial"),
    _t("fair value", "valor razonable", "financial"),
    _t("book value", "valor en libros", "financial"),
    _t("price-to-earnings", "precio-beneficio", "financial"),
    _t("earnings", "utilidades", "financial", notes="LatAm: utilidades; Spain: beneficios"),
)

# ── Technical Analysis ────────────────────────────────────────────────────────
_TA: tuple[Term, ...] = (
    _t("technical analysis", "análisis técnico", "technical_analysis"),
    _t("support", "soporte", "technical_analysis"),
    _t("resistance", "resistencia", "technical_analysis"),
    _t("trend", "tendencia", "technical_analysis"),
    _t("uptrend", "tendencia alcista", "technical_analysis"),
    _t("downtrend", "tendencia bajista", "technical_analysis"),
    _t("moving average", "media móvil", "technical_analysis"),
    _t("exponential moving average", "media móvil exponencial", "technical_analysis"),
    _t("relative strength index", "índice de fuerza relativa", "technical_analysis"),
    _t("bollinger bands", "bandas de Bollinger", "technical_analysis", notes="proper noun kept"),
    _t("macd", "MACD", "technical_analysis", notes="acronym kept"),
    _t("rsi", "RSI", "technical_analysis"),
    _t("candlestick", "vela", "technical_analysis"),
    _t("chart", "gráfico", "technical_analysis"),
    _t("breakout", "ruptura", "technical_analysis"),
    _t("breakdown", "quiebre", "technical_analysis"),
    _t("divergence", "divergencia", "technical_analysis"),
    _t("momentum", "impulso", "technical_analysis"),
    _t("oscillator", "oscilador", "technical_analysis"),
    _t("indicator", "indicador", "technical_analysis"),
    _t("timeframe", "temporalidad", "technical_analysis"),
    _t("horizon", "horizonte", "technical_analysis"),
    _t("forecast", "pronóstico", "technical_analysis"),
    _t("prediction", "predicción", "technical_analysis", plural_es="predicciones"),
    _t("accuracy", "precisión", "technical_analysis"),
    _t("confidence", "confianza", "technical_analysis"),
    _t("correlation", "correlación", "technical_analysis"),
)

# ── Sapphire-specific ─────────────────────────────────────────────────────────
_SAPPHIRE: tuple[Term, ...] = (
    _t(
        "kill switch",
        "interruptor de apagado",
        "sapphire",
        notes="Sapphire security-critical term — see lib/core/kill_switch.py",
    ),
    _t("signal", "señal", "sapphire"),
    _t("signal enhancement", "mejora de señal", "sapphire"),
    _t("regime", "régimen", "sapphire"),
    _t("regime detection", "detección de régimen", "sapphire", notes="see lib/analytics/regime.py"),
    _t("backtest", "prueba histórica", "sapphire"),
    _t("paper trading", "operación en papel", "sapphire"),
    _t("paper portfolio", "cartera en papel", "sapphire"),
    _t("agent", "agente", "sapphire"),
    _t("event bus", "bus de eventos", "sapphire"),
    _t("heartbeat", "latido", "sapphire"),
    _t("threat intel", "inteligencia de amenazas", "sapphire"),
    _t("dashboard", "tablero", "sapphire"),
    _t("brief", "informe", "sapphire"),
    _t("digest", "resumen", "sapphire"),
    _t("pulse", "pulso", "sapphire"),
    _t("scanner", "escáner", "sapphire"),
)

# ── Risk ──────────────────────────────────────────────────────────────────────
_RISK: tuple[Term, ...] = (
    _t("risk", "riesgo", "risk"),
    _t("reward", "recompensa", "risk"),
    _t("risk management", "gestión de riesgo", "risk"),
    _t("position sizing", "dimensionamiento de posición", "risk"),
    _t("drawdown", "caída máxima", "risk"),
    _t("max drawdown", "caída máxima histórica", "risk"),
    _t("volatility target", "objetivo de volatilidad", "risk"),
    _t("sharpe ratio", "índice de Sharpe", "risk"),
    _t("sortino ratio", "índice de Sortino", "risk"),
    _t("value at risk", "valor en riesgo", "risk"),
    _t("stress test", "prueba de estrés", "risk"),
    _t("counterparty risk", "riesgo de contraparte", "risk"),
    _t("systemic risk", "riesgo sistémico", "risk"),
    _t("black swan", "cisne negro", "risk"),
    _t("tail risk", "riesgo de cola", "risk"),
)

# ── Common cross-cutting terms ────────────────────────────────────────────────
_COMMON: tuple[Term, ...] = (
    _t("computer", "computadora", "common", notes="LatAm: computadora; Spain: ordenador"),
    _t("data", "datos", "common"),
    _t("data source", "fuente de datos", "common", plural_es="fuentes de datos"),
    _t("data sources", "fuentes de datos", "common"),
    _t("source", "fuente", "common"),
    _t("sources", "fuentes", "common"),
    _t("open", "abierto", "common"),
    _t("closed", "cerrado", "common"),
    _t("weekly", "semanal", "common"),
    _t("daily", "diario", "common"),
    _t("monthly", "mensual", "common"),
    _t("thread", "hilo", "common"),
    _t("post", "publicación", "common"),
    _t("update", "actualización", "common"),
    _t("summary", "resumen", "common"),
    _t("report", "reporte", "common", notes="LatAm: reporte; Spain also uses informe"),
    _t("analysis", "análisis", "common"),
    _t("market", "mercado", "common"),
    _t("price", "precio", "common"),
    _t("open positions", "posiciones abiertas", "common"),
    _t("event", "evento", "common"),
    _t("events", "eventos", "common"),
    _t("device", "dispositivo", "common"),
    _t("devices", "dispositivos", "common"),
    _t("project", "proyecto", "common"),
    _t("projects", "proyectos", "common"),
    _t("this week", "esta semana", "common"),
    _t("this cycle", "este ciclo", "common"),
    _t("across", "en", "common"),
    _t("logged", "registrados", "common"),
    _t("prioritized", "priorizados", "common"),
    _t("exploited in the wild", "explotado en la práctica", "common"),
    _t("informational only", "solo con fines informativos", "common"),
    _t("not investment advice", "no es asesoría de inversión", "common"),
    _t(
        "informational and educational purposes only",
        "solo con fines informativos y educativos",
        "common",
    ),
    _t("disclaimer", "descargo de responsabilidad", "common"),
)


_ALL_TERMS: tuple[Term, ...] = (
    *_TRADING,
    *_CRYPTO,
    *_FINANCIAL,
    *_TA,
    *_SAPPHIRE,
    *_RISK,
    *_COMMON,
)


def _build_glossary() -> dict[str, Term]:
    out: dict[str, Term] = {}
    for term in _ALL_TERMS:
        key = term.en.lower()
        if key in out:
            raise ValueError(f"duplicate glossary entry for {key!r}")
        out[key] = term
    return out


GLOSSARY: dict[str, Term] = _build_glossary()


def lookup(en: str) -> Term | None:
    """Case-insensitive term lookup. Returns None if not found."""
    if en is None:
        return None
    return GLOSSARY.get(en.strip().lower())


def all_terms() -> Iterator[Term]:
    """Yield every Term. Iteration order is stable (definition order)."""
    yield from GLOSSARY.values()


def terms_by_category() -> dict[str, list[Term]]:
    """Group terms by category. Every declared category appears (empty allowed)."""
    out: dict[str, list[Term]] = {cat: [] for cat in CATEGORIES}
    for term in GLOSSARY.values():
        out.setdefault(term.category, []).append(term)
    return out
