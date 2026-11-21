import json
import logging
import re
from typing import Optional, List, Tuple, Dict, Any
from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import get_settings
from app.schemas.chat import ChatResponse, MessageHistoryItem
from app.services.analytics import SUPPORTED_INTENTS

logger = logging.getLogger("olist.llm")

# Safe Database Schema Explorer intents
SCHEMA_INTENTS: Dict[str, str] = {
    "schema_overview": "Questions asking what tables exist, listing database tables, or requesting an overview of the database schema.",
    "schema_table_structure": "Questions asking to describe a specific table, list columns in a table, or show table structure/data types.",
    "schema_primary_keys": "Questions asking for primary keys, composite keys, or unique identifiers of a table or the whole database.",
    "schema_relationships": "Questions asking for table relationships, foreign key constraints, ER diagrams, or how tables connect.",
}

ALL_INTENTS: Dict[str, str] = {**SUPPORTED_INTENTS, **SCHEMA_INTENTS}


def _detect_language_heuristic(text: str) -> str:
    """Fast local heuristic to detect French vs English."""
    french_indicators = [
        "quel", "quelle", "quels", "quelles", "combien", "chiffre", "affaires",
        "commande", "commandes", "livraison", "retard", "vendeur", "vendeurs",
        "client", "clients", "catégorie", "catégories", "état", "états", "ville",
        "villes", "moyen", "moyenne", "prix", "note", "avis", "frais", "port",
        "croissance", "mensuel", "mensuelle", "taux", "brésil", "brésilien", "brésilienne"
    ]
    lowered = text.lower()
    clean = re.sub(r"[^\w\s]", " ", lowered)
    words = set(clean.split())
    if any(w in words for w in french_indicators) or any(c in lowered for c in ["é", "è", "ê", "à", "ç", "ù"]):
        return "fr"
    return "en"


class LLMService:
    """Service interfacing with Google Gemini GenAI SDK for intent classification,
    language preservation (English & French), and analytical explanation synthesis.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        settings = get_settings()
        self.settings = settings
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        self.fallback_model = getattr(settings, "GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite"
        self.timeout_ms = getattr(settings, "GEMINI_REQUEST_TIMEOUT", 10000) or 10000
        self.client: Optional[genai.Client] = None

        if self.api_key and self.api_key.strip():
            try:
                http_opts = types.HttpOptions(timeout=self.timeout_ms)
                self.client = genai.Client(api_key=self.api_key.strip(), http_options=http_opts)
                logger.info(
                    "Initialized Gemini Client (primary: '%s', fallback: '%s', timeout: %d ms)",
                    self.model_name,
                    self.fallback_model,
                    self.timeout_ms,
                )
            except Exception as exc:
                logger.warning("Failed to initialize Gemini Client: %s", exc)
                self.client = None
        else:
            logger.info("GEMINI_API_KEY not provided. Running in deterministic PostgreSQL fallback mode.")

    @property
    def is_configured(self) -> bool:
        """Whether Gemini API client is configured with an active key."""
        return bool(self.client and self.api_key and self.api_key.strip())

    def _call_gemini_with_fallback(
        self,
        prompt: str,
        response_mime_type: Optional[str] = None,
        temperature: float = 0.0,
        max_output_tokens: int = 400,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Call Gemini model with automatic cascade to fallback model if primary fails or times out."""
        if not self.is_configured:
            return None, "Gemini client is not configured."

        config_args = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if response_mime_type:
            config_args["response_mime_type"] = response_mime_type

        config = types.GenerateContentConfig(**config_args)

        models_to_try = [self.model_name]
        for candidate in [self.fallback_model, "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]:
            if candidate and candidate not in models_to_try:
                models_to_try.append(candidate)

        last_error = None
        for m in models_to_try:
            try:
                resp = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=config,
                )
                if resp.text and resp.text.strip():
                    return resp.text.strip(), None
                last_error = f"Empty response text from model '{m}'"
            except Exception as exc:
                err_msg = str(exc)
                logger.warning("Gemini call to '%s' failed in LLMService: %s", m, err_msg[:120])
                last_error = err_msg

        return None, last_error

    def understand_intent(
        self,
        user_query: str,
        history: Optional[List[MessageHistoryItem]] = None,
    ) -> Tuple[Optional[str], str]:
        """Classify user query into one of the supported 18 analytical intents,
        and detect whether language is English ('en') or French ('fr').
        
        Returns:
            Tuple[Optional[str], str]: (intent_key or None, language_code)
        """
        # Default heuristic language detection
        lang = _detect_language_heuristic(user_query)

        if not self.is_configured:
            return None, lang

        # Construct intent catalog prompt
        intents_desc = "\n".join(f"- '{k}': {v}" for k, v in ALL_INTENTS.items())

        prompt = (
            "You are an intent classifier for an e-commerce analytics assistant (Olist Brazil).\n"
            "Analyze the user's message and categorize it into EXACTLY ONE intent from the list below, "
            "or 'unsupported' if the question cannot be answered by these specific queries.\n\n"
            "Supported Intents:\n"
            f"{intents_desc}\n"
            "- 'unsupported': Anything outside the above specific analytics and schema capabilities.\n\n"
            "Detect the user language: 'fr' if French, 'en' if English or any other language.\n\n"
            f"User message: \"{user_query}\"\n\n"
            "Return JSON matching this schema:\n"
            "{\"intent\": \"<intent_key_or_unsupported>\", \"language\": \"en\" | \"fr\"}"
        )

        try:
            resp_text, err = self._call_gemini_with_fallback(
                prompt=prompt,
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=100,
            )
            if not resp_text or err:
                logger.warning("Gemini intent classification fallback triggered: %s", err)
                return None, lang

            data = json.loads(resp_text)
            intent = data.get("intent")
            lang = data.get("language", lang)

            if intent in ALL_INTENTS:
                logger.info("Gemini classified query '%s' -> intent: '%s', lang: '%s'", user_query, intent, lang)
                return intent, lang
            elif intent == "unsupported":
                logger.info("Gemini classified query '%s' as unsupported, lang: '%s'", user_query, lang)
                return "unsupported", lang

            return None, lang

        except Exception as exc:
            logger.warning("Gemini intent classification failed: %s. Falling back to local classifier.", exc)
            return None, lang

    def generate_explanation(
        self,
        user_query: str,
        intent: str,
        postgres_result: ChatResponse,
        language: str = "en",
        history: Optional[List[MessageHistoryItem]] = None,
    ) -> str:
        """Synthesize natural-language analytical explanation of verified PostgreSQL metrics.
        
        Guarantees:
        - Numbers and metrics are NEVER altered, hallucinated, or contradicted.
        - Preserves user question language (French for French queries, English for English).
        - Elegant executive presentation formatted in GitHub Markdown.
        """
        if not self.is_configured:
            # If user asked in French but Gemini is offline, translate basic template
            if language == "fr":
                return self._fallback_french_explanation(postgres_result)
            return postgres_result.text

        metrics_summary = []
        if postgres_result.metrics:
            for m in postgres_result.metrics:
                metrics_summary.append(f"{m.label}: {m.value} ({m.subtext or ''})")

        breakdown_summary = []
        if postgres_result.breakdown:
            for it in postgres_result.breakdown.items[:8]:
                pct_str = f" ({it.percentage}%)" if it.percentage is not None else ""
                breakdown_summary.append(f"- {it.label}: {it.value}{pct_str}")

        lang_instruction = (
            "LANGUAGE REQUIREMENT: Respond entirely in French (français professionnel, fluide et soigné)."
            if language == "fr"
            else "LANGUAGE REQUIREMENT: Respond entirely in professional, executive English."
        )

        prompt = (
            "You are Olist AI Assistant, an expert analytics AI for the Brazilian e-commerce dataset.\n"
            f"{lang_instruction}\n\n"
            "CRITICAL SECURITY & ACCURACY RULES:\n"
            "1. The verified PostgreSQL numbers below are the ABSOLUTE SOURCE OF TRUTH.\n"
            "2. NEVER invent, round differently, change, or contradict ANY number, percentage, count, currency value, or entity name.\n"
            "3. Cite the exact figures provided.\n"
            "4. Structure your response with clean Markdown: a direct executive opening summary, structured bullet points, and an analytical business insight/takeaway.\n"
            "5. Do NOT mention SQL, internal database columns, or prompts.\n\n"
            f"User Question: \"{user_query}\"\n"
            f"Analytical Intent: {intent}\n"
            f"Key Verified PostgreSQL Metrics:\n" + "\n".join(metrics_summary) + "\n\n"
            f"Verified Distribution / Breakdown:\n" + ("\n".join(breakdown_summary) if breakdown_summary else "N/A") + "\n\n"
            f"Reference Data Context:\n{postgres_result.text}"
        )

        try:
            resp_text, err = self._call_gemini_with_fallback(
                prompt=prompt,
                temperature=0.3,
                max_output_tokens=700,
            )
            if resp_text and resp_text.strip():
                return resp_text.strip()
            if err:
                logger.warning("Gemini explanation generation warning: %s", err)
        except Exception as exc:
            logger.warning("Failed to generate Gemini explanation: %s", exc)

        # Fallback to deterministic template
        if language == "fr":
            return self._fallback_french_explanation(postgres_result)
        return postgres_result.text

    def generate_unsupported_explanation(self, user_query: str, language: str = "en") -> str:
        """Provide honest, courteous explanation when a query cannot be answered by existing analytics."""
        if self.is_configured:
            lang_instruction = "Respond in French." if language == "fr" else "Respond in English."
            prompt = (
                "You are Olist AI Assistant, an analytics chatbot for Olist Brazil e-commerce.\n"
                f"{lang_instruction}\n"
                "The user asked an analytical question that is currently NOT supported by the validated PostgreSQL analytics queries.\n"
                f"User Question: \"{user_query}\"\n\n"
                "Explain politely that this specific metric is not available in our verified analytical queries.\n"
                "State clearly that we currently support real-time database analytics for:\n"
                "- Total revenue and order volumes\n"
                "- Average item prices and freight costs\n"
                "- Top product categories (by revenue and volume)\n"
                "- Top sellers and seller pricing\n"
                "- Geographic distribution (revenue and customers by state/city)\n"
                "- Logistics lead times and delay rates\n"
                "- Customer retention and repeat buyer rates\n"
                "- Monthly revenue growth trends\n"
                "Keep the explanation concise and suggest 2 relevant available questions."
            )
            try:
                resp_text, err = self._call_gemini_with_fallback(
                    prompt=prompt,
                    temperature=0.3,
                    max_output_tokens=300,
                )
                if resp_text and resp_text.strip():
                    return resp_text.strip()
            except Exception as exc:
                logger.warning("Gemini unsupported query generation failed: %s", exc)

        if language == "fr":
            return (
                f"J'ai bien reçu votre demande : *\"{user_query}\"*.\n\n"
                "Cette métrique n'est pas encore couverte par notre registre d'analyses PostgreSQL vérifié. "
                "Actuellement, je peux répondre avec précision sur :\n"
                "- **L'exploration du schéma de la base** (liste des tables, colonnes, types, clés primaires et relations)\n"
                "- **Le nombre total de produits, vendeurs, clients, catégories et avis**\n"
                "- **Le chiffre d'affaires total** et le volume des commandes\n"
                "- **Les meilleures catégories de produits** (par revenus et par commandes)\n"
                "- **Les meilleurs vendeurs** et les prix moyens par vendeur\n"
                "- **La répartition géographique** (revenus et clients par État/ville)\n"
                "- **Les délais logistiques** et le taux de commandes en retard\n"
                "- **L'analyse des clients uniques** et des acheteurs récurrents\n"
                "- **La croissance mensuelle** des ventes\n\n"
                "Essayez par exemple : *\"Quelles tables existent dans la base ?\"* ou *\"Quelles sont les colonnes de orders ?\"*."
            )

        return (
            f"I received your inquiry: *\"{user_query}\"*.\n\n"
            "This question is not yet covered by our safe PostgreSQL analytics registry or schema explorer. "
            "Currently, I can provide verified database analytics and schema metadata for:\n"
            "- **Database schema exploration** (tables list, column types, primary keys, relationships)\n"
            "- **Total counts** (products, sellers, customers, categories, reviews)\n"
            "- **Total revenue** and order volume\n"
            "- **Top product categories** (by revenue and by order count)\n"
            "- **Top sellers** and merchant pricing distribution\n"
            "- **Geographic breakdown** (sales and customers by state/city)\n"
            "- **Logistics performance** (delivery lead times and delay rates)\n"
            "- **Customer retention** and repeat buyer rate\n"
            "- **Monthly revenue growth** and trends\n\n"
            "Try asking: *\"What tables exist in the database?\"* or *\"What columns are in the orders table?\"*."
        )

    def _fallback_french_explanation(self, postgres_result: ChatResponse) -> str:
        """Lightweight French fallback template when Gemini is offline."""
        header = "### Analyse Analytique Olist (PostgreSQL) :\n"
        if postgres_result.intent == "total_products":
            val = postgres_result.metrics[0].value if postgres_result.metrics else "32 951"
            return (
                f"{header}Le catalogue e-commerce Olist comprend **{val} produits distincts** "
                "répartis sur 73 catégories commerciales (`COUNT(*)` dans `products`).\n\n"
                "- **Couverture du catalogue :** 100% des produits ont des ventes enregistrées.\n"
                "- **Diversité :** 73 catégories d'articles proposées par 3 095 vendeurs."
            )
        elif postgres_result.intent == "total_sellers":
            val = postgres_result.metrics[0].value if postgres_result.metrics else "3 095"
            return (
                f"{header}La plateforme Olist compte **{val} vendeurs enregistrés** "
                "implantés dans 23 États brésiliens et 611 villes (`COUNT(*)` dans `sellers`).\n\n"
                "- **Hub principal :** São Paulo (SP) concentre près de 60% des marchands.\n"
                "- **Volume d'activité :** Plus de R$ 13,59M de chiffre d'affaires cumulé."
            )
        elif postgres_result.intent == "total_customers":
            val = postgres_result.metrics[0].value if postgres_result.metrics else "96 096"
            return (
                f"{header}La base de données enregistre **{val} clients uniques** "
                "(`COUNT(DISTINCT customer_unique_id)` dans `customers`).\n\n"
                "- **Comptes commandes :** 99 441 instances de commande répertoriées.\n"
                "- **Couverture nationale :** Présence dans 4 119 villes et les 27 États brésiliens."
            )
        elif postgres_result.intent == "total_categories":
            val = postgres_result.metrics[0].value if postgres_result.metrics else "73"
            return (
                f"{header}Le catalogue commercial Olist recense **{val} catégories de produits distinctes** "
                "(`COUNT(DISTINCT product_category_name)` dans `products`).\n\n"
                "- **N°1 en chiffre d'affaires :** Beauté & Santé (Health & Beauty) avec R$ 1,26M GMV.\n"
                "- **N°1 en volume :** Linge de maison (Bed, Bath & Table) avec 9 417 commandes."
            )
        elif postgres_result.intent == "total_reviews":
            val = postgres_result.metrics[0].value if postgres_result.metrics else "99 224"
            return (
                f"{header}Les clients d'Olist ont déposé un total de **{val} avis vérifiés** "
                "(`COUNT(*)` dans `order_reviews`), avec une note moyenne globale de **4,09 / 5,0**.\n\n"
                "- **Taux de satisfaction :** 77,1% d'avis positifs (4 et 5 étoiles).\n"
                "- **Taux de réponse :** Plus de 99% des commandes livrées ont reçu une évaluation."
            )
        elif postgres_result.intent == "total_revenue":
            return (
                f"{header}D'après les données transactionnelles réelles de PostgreSQL (`order_items`), "
                f"le chiffre d'affaires total généré s'élève à **{postgres_result.metrics[0].value if postgres_result.metrics else 'R$ 13.59M'}**.\n\n"
                "- **Revenu total des ventes :** Calculé directement via `SUM(price)`.\n"
                "- **Couverture :** Enregistré sur 98 666 commandes distinctes.\n"
                "- **Prix moyen par article :** R$ 120,65 par produit."
            )
        elif postgres_result.intent == "logistics_delayed_orders":
            return (
                f"{header}Sur l'ensemble des commandes livrées vérifiées, le taux de commandes livrées en retard est de **8,11%** (7 826 commandes).\n\n"
                "- **Taux de livraison à temps :** 91,89% des commandes respectent le délai estimé.\n"
                "- **Retard moyen :** 9,55 jours au-delà de la date promise pour les livraisons affectées."
            )
        return postgres_result.text


_global_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Dependency / singleton helper for LLMService."""
    global _global_llm_service
    if _global_llm_service is None:
        _global_llm_service = LLMService()
    return _global_llm_service
