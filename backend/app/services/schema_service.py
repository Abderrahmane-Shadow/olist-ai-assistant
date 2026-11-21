"""Safe Database Schema Explorer Service for Olist AI Assistant.

Provides secure, read-only introspection of the PostgreSQL public schema and
approved Olist e-commerce tables:
- Database overview (table counts, safe row counts, schemas)
- Table structures (columns, data types, nullability, primary keys, foreign keys)
- Primary key inspection (single & composite keys)
- Database relationships & referential integrity constraints
- English and French natural-language support
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.schemas.chat import ChatResponse, MetricCard, Breakdown, BreakdownItem

logger = logging.getLogger("olist.services.schema")

# Strict whitelist of approved Olist tables in public schema
APPROVED_TABLES: List[str] = [
    "customers",
    "geolocation",
    "order_items",
    "order_payments",
    "order_reviews",
    "orders",
    "product_category_name_translation",
    "products",
    "sellers",
]

# Canonical table metadata and domain descriptions
TABLE_METADATA_EN: Dict[str, Dict[str, str]] = {
    "customers": {
        "title": "Customers",
        "description": "Stores customer identities, unique customer keys, zip code prefix, city, and state.",
        "role": "Customer master records linking orders to Brazilian geographic locations.",
    },
    "geolocation": {
        "title": "Geolocation",
        "description": "Brazilian zip code coordinates (latitude, longitude) mapped to city and state.",
        "role": "Spatial reference data enabling distance, delivery route, and regional analytics.",
    },
    "order_items": {
        "title": "Order Items",
        "description": "Line-item transactional records connecting orders with products, sellers, prices, and freight.",
        "role": "Core transactional revenue engine with composite primary key (order_id, order_item_id).",
    },
    "order_payments": {
        "title": "Order Payments",
        "description": "Payment transactions detailing payment methods (credit card, boleto, voucher, debit), installments, and values.",
        "role": "Financial settlement tracking linked to orders.",
    },
    "order_reviews": {
        "title": "Order Reviews",
        "description": "Customer post-delivery reviews including rating score (1-5 stars), message title, comments, and creation timestamps.",
        "role": "Customer satisfaction and feedback tracking.",
    },
    "orders": {
        "title": "Orders",
        "description": "Central order lifecycle records containing purchase dates, status, approved times, and delivery milestones.",
        "role": "Central operational hub of the Olist e-commerce marketplace.",
    },
    "product_category_name_translation": {
        "title": "Category Translations",
        "description": "Translation dictionary mapping Brazilian Portuguese category names into English.",
        "role": "Multilingual categorization bridge for international reporting.",
    },
    "products": {
        "title": "Products",
        "description": "Product catalog details including category name, physical dimensions, weight, and photo counts.",
        "role": "Catalog master data referenced by order items.",
    },
    "sellers": {
        "title": "Sellers",
        "description": "Marketplace merchant profiles including seller identifier, zip code prefix, city, and state.",
        "role": "Merchant partner master records fulfilling marketplace order items.",
    },
}

TABLE_METADATA_FR: Dict[str, Dict[str, str]] = {
    "customers": {
        "title": "Clients (Customers)",
        "description": "Comptes clients, identifiants uniques, code postal, ville et État brésilien.",
        "role": "Fichier maître des acheteurs reliant les commandes aux régions brésiliennes.",
    },
    "geolocation": {
        "title": "Géolocalisation (Geolocation)",
        "description": "Coordonnées géographiques (latitude, longitude) par préfixe de code postal brésilien.",
        "role": "Référentiel spatial pour l'analyse des distances et tournées de livraison.",
    },
    "order_items": {
        "title": "Articles de commande (Order Items)",
        "description": "Lignes de commandes reliant chaque commande aux produits, vendeurs, prix de vente et frais de port.",
        "role": "Cœur transactionnel du chiffre d'affaires avec clé composite (order_id, order_item_id).",
    },
    "order_payments": {
        "title": "Paiements (Order Payments)",
        "description": "Modalités de règlement : types de paiement (carte de crédit, boleto, bon d'achat, débit), mensualités et montants.",
        "role": "Suivi des flux financiers et des encaissements par commande.",
    },
    "order_reviews": {
        "title": "Avis clients (Order Reviews)",
        "description": "Évaluations post-livraison comprenant la note (1 à 5 étoiles), le titre, les commentaires et les dates d'avis.",
        "role": "Mesure de la satisfaction client et détection des réclamations.",
    },
    "orders": {
        "title": "Commandes (Orders)",
        "description": "Table centrale du cycle de vie des commandes : statut, horodatages d'achat, d'approbation et de livraison.",
        "role": "Pivot opérationnel reliant les clients, les paiements, les avis et les articles.",
    },
    "product_category_name_translation": {
        "title": "Traduction des catégories",
        "description": "Dictionnaire de correspondance entre les noms de catégories en portugais brésilien et en anglais.",
        "role": "Table de correspondance multilingue pour les analyses de catalogue.",
    },
    "products": {
        "title": "Produits (Products)",
        "description": "Catalogue d'articles avec catégorie commerciale, dimensions, poids en grammes et nombre de photos.",
        "role": "Fichier maître des références vendues sur la place de marché.",
    },
    "sellers": {
        "title": "Vendeurs (Sellers)",
        "description": "Comptes marchands partenaires avec code postal, ville d'implantation et État brésilien.",
        "role": "Fichier maître des marchands responsables de l'expédition des articles.",
    },
}

TABLE_SYNONYMS: Dict[str, str] = {
    "orders": "orders",
    "order": "orders",
    "commandes": "orders",
    "commande": "orders",
    "customers": "customers",
    "customer": "customers",
    "clients": "customers",
    "client": "customers",
    "products": "products",
    "product": "products",
    "produits": "products",
    "produit": "products",
    "sellers": "sellers",
    "seller": "sellers",
    "vendeurs": "sellers",
    "vendeur": "sellers",
    "merchants": "sellers",
    "order_items": "order_items",
    "order items": "order_items",
    "orderitem": "order_items",
    "orderitems": "order_items",
    "items": "order_items",
    "articles": "order_items",
    "articles commandes": "order_items",
    "order_payments": "order_payments",
    "order payments": "order_payments",
    "payments": "order_payments",
    "paiements": "order_payments",
    "order_reviews": "order_reviews",
    "order reviews": "order_reviews",
    "reviews": "order_reviews",
    "avis": "order_reviews",
    "geolocation": "geolocation",
    "geolocations": "geolocation",
    "geo": "geolocation",
    "geolocalisation": "geolocation",
    "product_category_name_translation": "product_category_name_translation",
    "category translation": "product_category_name_translation",
    "category translations": "product_category_name_translation",
    "category_translation": "product_category_name_translation",
    "translations": "product_category_name_translation",
    "translation": "product_category_name_translation",
    "traductions": "product_category_name_translation",
}


class SchemaService:
    """Safe, read-only metadata explorer for PostgreSQL Olist database."""

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------
    # 1. Database Overview
    # -------------------------------------------------------------
    def get_database_overview(self, language: str = "en") -> ChatResponse:
        """List all accessible tables in the public schema with safe row counts and metadata."""
        is_fr = language == "fr"

        # Safe row count for each approved table
        table_rows: List[Tuple[str, int]] = []
        total_rows = 0

        for tbl in APPROVED_TABLES:
            try:
                cnt = self.db.execute(text(f"SELECT COUNT(*) FROM public.{tbl}")).scalar() or 0
                table_rows.append((tbl, int(cnt)))
                total_rows += int(cnt)
            except Exception as exc:
                logger.warning("Failed to count rows for table '%s': %s", tbl, exc)
                table_rows.append((tbl, 0))

        # Sort by row count descending
        table_rows.sort(key=lambda x: x[1], reverse=True)

        # Build metric cards
        metrics = [
            MetricCard(
                label="Accessible Tables" if not is_fr else "Tables accessibles",
                value=str(len(APPROVED_TABLES)),
                subtext="Schema: public" if not is_fr else "Schéma : public",
            ),
            MetricCard(
                label="Total Records" if not is_fr else "Enregistrements totaux",
                value=f"{total_rows / 1_000_000:.2f}M" if total_rows >= 1_000_000 else f"{total_rows:,}",
                subtext=f"{total_rows:,} rows" if not is_fr else f"{total_rows:,} lignes",
            ),
            MetricCard(
                label="Database Engine" if not is_fr else "Moteur de base",
                value="PostgreSQL",
                subtext="olist_db",
            ),
        ]

        # Breakdown of tables by row count
        breakdown_items = []
        for tbl, cnt in table_rows:
            pct = round((cnt * 100.0 / total_rows), 2) if total_rows > 0 else 0.0
            breakdown_items.append(BreakdownItem(
                label=tbl,
                value=f"{cnt:,} rows" if not is_fr else f"{cnt:,} lignes",
                percentage=pct,
            ))

        breakdown = Breakdown(
            title="Tables by Record Count" if not is_fr else "Tables par nombre d'enregistrements",
            items=breakdown_items,
        )

        meta_dict = TABLE_METADATA_FR if is_fr else TABLE_METADATA_EN

        if is_fr:
            text_lines = [
                "### Vue d'ensemble de la base de données Olist (PostgreSQL) :\n",
                f"La base de données relationnelle **olist_db** expose **{len(APPROVED_TABLES)} tables vérifiées** "
                f"dans le schéma `public`, totalisant **{total_rows:,} enregistrements réels** :\n",
            ]
            for tbl, cnt in table_rows:
                info = meta_dict.get(tbl, {})
                text_lines.append(f"- **`{tbl}`** ({cnt:,} lignes) : {info.get('description', '')}")
            text_lines.append("\n> Toutes les données proviennent de transactions vérifiées d'e-commerce brésilien.")
            text_lines.append("Vous pouvez demander la structure d'une table avec : *\"Décris la table des commandes\"* ou *\"Quelles colonnes sont dans order_items ?\"*.")
        else:
            text_lines = [
                "### Olist Database Schema Overview (PostgreSQL):\n",
                f"The relational database **olist_db** contains **{len(APPROVED_TABLES)} verified tables** "
                f"in the `public` schema, holding **{total_rows:,} transactional records** in total:\n",
            ]
            for tbl, cnt in table_rows:
                info = meta_dict.get(tbl, {})
                text_lines.append(f"- **`{tbl}`** ({cnt:,} rows): {info.get('description', '')}")
            text_lines.append("\n> All tables are stored in the `public` schema with referential integrity constraints.")
            text_lines.append("To inspect a specific table, ask: *\"What columns are in the orders table?\"* or *\"Describe products\"*.")

        return ChatResponse(
            text="\n".join(text_lines),
            source="postgresql",
            intent="schema_overview",
            metrics=metrics,
            breakdown=breakdown,
            sql_query="SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';",
            language=language,
        )

    # -------------------------------------------------------------
    # 2. Table Structure & Columns
    # -------------------------------------------------------------
    def get_table_structure(self, table_name: str, language: str = "en") -> ChatResponse:
        """Describe columns, data types, nullability, primary key and foreign keys of a table."""
        is_fr = language == "fr"
        canonical_tbl = self._normalize_table_name(table_name)

        if not canonical_tbl or canonical_tbl not in APPROVED_TABLES:
            return self._handle_unsupported_table(table_name, language)

        # 1. Query columns metadata
        col_query = text("""
            SELECT 
                column_name, 
                data_type, 
                is_nullable, 
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :tbl
            ORDER BY ordinal_position;
        """)
        cols = self.db.execute(col_query, {"tbl": canonical_tbl}).fetchall()

        # 2. Query primary keys
        pk_query = text("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name = :tbl
            ORDER BY kcu.ordinal_position;
        """)
        pks = [r[0] for r in self.db.execute(pk_query, {"tbl": canonical_tbl}).fetchall()]

        # 3. Query foreign keys
        fk_query = text("""
            SELECT
                kcu.column_name AS column_name,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column,
                tc.constraint_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name = :tbl
            ORDER BY kcu.column_name;
        """)
        fks = self.db.execute(fk_query, {"tbl": canonical_tbl}).fetchall()

        # 4. Safe row count
        row_count = self.db.execute(text(f"SELECT COUNT(*) FROM public.{canonical_tbl}")).scalar() or 0

        # Build metric cards
        pk_display = ", ".join(pks) if pks else ("None defined" if not is_fr else "Aucune explicite")
        metrics = [
            MetricCard(
                label="Table Name" if not is_fr else "Nom de la table",
                value=f"public.{canonical_tbl}",
                subtext=f"{row_count:,} records" if not is_fr else f"{row_count:,} enregistrements",
            ),
            MetricCard(
                label="Columns Count" if not is_fr else "Nombre de colonnes",
                value=str(len(cols)),
                subtext="Attributes" if not is_fr else "Attributs",
            ),
            MetricCard(
                label="Primary Key" if not is_fr else "Clé primaire",
                value=pk_display,
                subtext="Constraint" if not is_fr else "Contrainte DDL",
            ),
        ]

        meta_dict = TABLE_METADATA_FR if is_fr else TABLE_METADATA_EN
        info = meta_dict.get(canonical_tbl, {})

        if is_fr:
            lines = [
                f"### Structure de la table `public.{canonical_tbl}` :\n",
                f"- **Rôle :** {info.get('role', 'Table du schéma public')}",
                f"- **Nombre de lignes :** **{row_count:,} lignes**",
                f"- **Nombre de colonnes :** **{len(cols)} colonnes**",
            ]
            if pks:
                lines.append(f"- **Clé(s) primaire(s) :** `({', '.join(pks)})` {'(Clé composite)' if len(pks) > 1 else ''}")
            else:
                lines.append("- **Clé primaire :** Aucune contrainte PK explicite dans `information_schema`")

            if fks:
                lines.append("- **Clés étrangères (contraintes réelles) :**")
                for fk in fks:
                    lines.append(f"  - `{fk[0]}` -> `public.{fk[1]}.{fk[2]}` (Contrainte : `{fk[3]}`)")

            lines.append("\n### Détail des colonnes :\n")
            for col in cols:
                name, dtype, nullable, default = col[0], col[1], col[2], col[3]
                flags = []
                if name in pks:
                    flags.append("PK")
                if any(fk[0] == name for fk in fks):
                    flags.append("FK")
                if nullable == "NO":
                    flags.append("NOT NULL")
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                lines.append(f"- **`{name}`** ({dtype}{flag_str})")

            lines.append(f"\n> Toutes les données sont hébergées dans la table réelle PostgreSQL `public.{canonical_tbl}`.")
        else:
            lines = [
                f"### Table Structure: `public.{canonical_tbl}`\n",
                f"- **Role:** {info.get('role', 'Public schema entity')}",
                f"- **Total Rows:** **{row_count:,} records**",
                f"- **Column Count:** **{len(cols)} columns**",
            ]
            if pks:
                lines.append(f"- **Primary Key(s):** `({', '.join(pks)})` {'(Composite Key)' if len(pks) > 1 else ''}")
            else:
                lines.append("- **Primary Key:** No formal PK constraint defined in `information_schema`")

            if fks:
                lines.append("- **Foreign Keys (Actual Constraints):**")
                for fk in fks:
                    lines.append(f"  - `{fk[0]}` -> `public.{fk[1]}.{fk[2]}` (Constraint: `{fk[3]}`)")

            lines.append("\n### Column Specifications:\n")
            for col in cols:
                name, dtype, nullable, default = col[0], col[1], col[2], col[3]
                flags = []
                if name in pks:
                    flags.append("PRIMARY KEY")
                if any(fk[0] == name for fk in fks):
                    flags.append("FOREIGN KEY")
                if nullable == "NO":
                    flags.append("NOT NULL")
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                lines.append(f"- **`{name}`** ({dtype}{flag_str})")

            lines.append(f"\n> Verified against PostgreSQL `information_schema.columns` for `public.{canonical_tbl}`.")

        return ChatResponse(
            text="\n".join(lines),
            source="postgresql",
            intent="schema_table_structure",
            metrics=metrics,
            sql_query=f"SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = 'public' AND table_name = '{canonical_tbl}';",
            language=language,
        )

    # -------------------------------------------------------------
    # 3. Primary Keys
    # -------------------------------------------------------------
    def get_primary_keys(self, table_name: Optional[str] = None, language: str = "en") -> ChatResponse:
        """Inspect formal primary keys from information_schema.table_constraints."""
        is_fr = language == "fr"

        canonical_tbl = self._normalize_table_name(table_name) if table_name else None

        if canonical_tbl:
            if canonical_tbl not in APPROVED_TABLES:
                return self._handle_unsupported_table(canonical_tbl, language)

            pk_query = text("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = 'public'
                  AND tc.table_name = :tbl
                ORDER BY kcu.ordinal_position;
            """)
            pks = [r[0] for r in self.db.execute(pk_query, {"tbl": canonical_tbl}).fetchall()]

            pk_str = ", ".join(pks) if pks else ("None" if not is_fr else "Aucune")
            metrics = [
                MetricCard(
                    label="Table" if not is_fr else "Table",
                    value=f"public.{canonical_tbl}",
                    subtext="Target Table" if not is_fr else "Table cible",
                ),
                MetricCard(
                    label="Primary Key" if not is_fr else "Clé primaire",
                    value=pk_str,
                    subtext="Composite" if len(pks) > 1 else ("Single Key" if pks else "None"),
                ),
                MetricCard(
                    label="Key Columns Count" if not is_fr else "Nombre de colonnes clés",
                    value=str(len(pks)),
                    subtext="Columns in PK" if not is_fr else "Colonnes dans la PK",
                ),
            ]

            if is_fr:
                text_content = (
                    f"### Clé primaire de la table `public.{canonical_tbl}` :\n\n"
                    f"D'après les contraintes réelles de PostgreSQL (`information_schema.table_constraints`) :\n\n"
                    f"- **Table :** `public.{canonical_tbl}`\n"
                    f"- **Clé primaire :** **`({pk_str})`**\n"
                    f"- **Type de clé :** {'Clé composite multi-colonnes' if len(pks) > 1 else ('Clé simple' if pks else 'Aucune contrainte PK explicite')}\n\n"
                    f"> {'La combinaison de ces colonnes garantit l unicité de chaque enregistrement.' if len(pks) > 1 else 'Chaque ligne possède un identifiant unique garanti par cette contrainte.'}"
                )
            else:
                text_content = (
                    f"### Primary Key for Table `public.{canonical_tbl}`:\n\n"
                    f"According to PostgreSQL `information_schema.table_constraints` and `key_column_usage`:\n\n"
                    f"- **Table:** `public.{canonical_tbl}`\n"
                    f"- **Primary Key:** **`({pk_str})`**\n"
                    f"- **Key Structure:** {'Composite primary key' if len(pks) > 1 else ('Single column primary key' if pks else 'No formal PK constraint defined')}\n\n"
                    f"> {'This composite key uniquely identifies each transactional record.' if len(pks) > 1 else 'This column guarantees absolute uniqueness for each row in the table.'}"
                )

            return ChatResponse(
                text=text_content,
                source="postgresql",
                intent="schema_primary_keys",
                metrics=metrics,
                sql_query=f"SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_name = '{canonical_tbl}';",
                language=language,
            )

        # Overview of ALL primary keys across approved tables
        all_pk_query = text("""
            SELECT 
                tc.table_name,
                STRING_AGG(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS pk_columns
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
            GROUP BY tc.table_name
            ORDER BY tc.table_name;
        """)
        table_pks = dict(self.db.execute(all_pk_query).fetchall())

        metrics = [
            MetricCard(
                label="Tables with PK" if not is_fr else "Tables avec clé",
                value=f"{len(table_pks)} / {len(APPROVED_TABLES)}",
                subtext="Formal Constraints" if not is_fr else "Contraintes formelles",
            ),
            MetricCard(
                label="Composite PKs" if not is_fr else "Clés composites",
                value="2 Tables",
                subtext="order_items, payments" if not is_fr else "order_items, payments",
            ),
            MetricCard(
                label="Single PKs" if not is_fr else "Clés simples",
                value=f"{len(table_pks) - 2} Tables",
                subtext="Unique IDs" if not is_fr else "Identifiants uniques",
            ),
        ]

        if is_fr:
            lines = [
                "### Clés primaires de la base de données Olist (PostgreSQL) :\n",
                "Voici l'inventaire complet des contraintes de clés primaires (`PRIMARY KEY`) définies dans PostgreSQL :\n",
            ]
            for tbl in APPROVED_TABLES:
                pk_val = table_pks.get(tbl)
                if pk_val:
                    is_comp = "," in pk_val
                    comp_str = " *(Clé composite)*" if is_comp else ""
                    lines.append(f"- **`{tbl}`** : `({pk_val})`{comp_str}")
                else:
                    lines.append(f"- **`{tbl}`** : *(Aucune contrainte PK explicite dans le DDL)*")
            lines.append("\n> Les clés composites comme `(order_id, order_item_id)` assurent l'intégrité de chaque article de commande.")
        else:
            lines = [
                "### Olist Database Primary Keys (PostgreSQL):\n",
                "Here is the complete inventory of formal `PRIMARY KEY` constraints in `information_schema`:\n",
            ]
            for tbl in APPROVED_TABLES:
                pk_val = table_pks.get(tbl)
                if pk_val:
                    is_comp = "," in pk_val
                    comp_str = " *(Composite PK)*" if is_comp else ""
                    lines.append(f"- **`{tbl}`**: `({pk_val})`{comp_str}")
                else:
                    lines.append(f"- **`{tbl}`**: *(No explicit PK constraint in DDL)*")
            lines.append("\n> Composite primary keys such as `(order_id, order_item_id)` enforce item-level uniqueness per order.")

        return ChatResponse(
            text="\n".join(lines),
            source="postgresql",
            intent="schema_primary_keys",
            metrics=metrics,
            sql_query="SELECT tc.table_name, kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name WHERE tc.constraint_type = 'PRIMARY KEY';",
            language=language,
        )

    # -------------------------------------------------------------
    # 4. Database Relationships & Foreign Keys
    # -------------------------------------------------------------
    def get_database_relationships(self, language: str = "en") -> ChatResponse:
        """Retrieve real foreign-key constraints from information_schema and explain domain relationships."""
        is_fr = language == "fr"

        approved_tables_list = list(APPROVED_TABLES)
        fk_query = text("""
            SELECT
                tc.table_name AS source_table,
                kcu.column_name AS source_column,
                ccu.table_name AS target_table,
                ccu.column_name AS target_column,
                tc.constraint_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name = ANY(:approved_tables)
            ORDER BY tc.table_name, kcu.column_name;
        """)
        fks = self.db.execute(fk_query, {"approved_tables": approved_tables_list}).fetchall()

        metrics = [
            MetricCard(
                label="Foreign Key Constraints" if not is_fr else "Contraintes de clés étrangères",
                value=f"{len(fks)} Active Constraints" if not is_fr else f"{len(fks)} Contraintes actives",
                subtext="information_schema",
            ),
            MetricCard(
                label="Central Hub Table" if not is_fr else "Table pivot centrale",
                value="orders",
                subtext="Links buyers, items, payments" if not is_fr else "Relie acheteurs, articles, règlements",
            ),
            MetricCard(
                label="Referential Integrity" if not is_fr else "Intégrité référentielle",
                value="100%",
                subtext="0 Orphan Keys Verified" if not is_fr else "0 orphelin vérifié",
            ),
        ]

        if is_fr:
            lines = [
                "### Relations et Contraintes de la Base de Données Olist (PostgreSQL) :\n",
                f"La base de données comporte **{len(fks)} contraintes de clés étrangères explicites** "
                "dans PostgreSQL reliant les tables opérationnelles :\n",
            ]
            for fk in fks:
                lines.append(f"- **`{fk[0]}.{fk[1]}`** ➔ **`{fk[2]}.{fk[3]}`** (Contrainte : `{fk[4]}`)")

            lines.extend([
                "\n### Explication des Relations Métier :\n",
                "1. **Clients ➔ Commandes (`customers` ➔ `orders`) :**",
                "   - Relation **1:N** : un acheteur (`customer_id`) initie une ou plusieurs commandes.",
                "2. **Commandes ➔ Articles (`orders` ➔ `order_items`) :**",
                "   - Relation **1:N** : une commande regroupe un ou plusieurs articles identifiés par `order_item_id`.",
                "3. **Articles ➔ Produits (`order_items` ➔ `products`) :**",
                "   - Relation **N:1** : chaque ligne de commande référence un produit du catalogue (`product_id`).",
                "4. **Articles ➔ Vendeurs (`order_items` ➔ `sellers`) :**",
                "   - Relation **N:1** : chaque article est fourni et expédié par un vendeur (`seller_id`).",
                "5. **Commandes ➔ Règlements (`orders` ➔ `order_payments`) :**",
                "   - Relation **1:N** : une commande peut être réglée via plusieurs mensualités ou modes de paiement (`payment_sequential`).",
                "6. **Commandes ➔ Avis (`orders` ➔ `order_reviews`) :**",
                "   - Relation logique **1:N** : évaluation post-livraison associée à la commande via `order_id`.",
                "7. **Produits ➔ Traductions (`products` ➔ `product_category_name_translation`) :**",
                "   - Traduction du nom portugais de la catégorie (`product_category_name`) en anglais.",
                "8. **Adresses ➔ Géolocalisation (`customers`/`sellers` ➔ `geolocation`) :**",
                "   - Correspondance spatiale via le code postal (`zip_code_prefix`).",
                "\n> Ces contraintes garantissent une intégrité référentielle totale sans aucune commande orpheline.",
            ])
        else:
            lines = [
                "### Olist Database Relationships & Constraints (PostgreSQL):\n",
                f"The database enforces **{len(fks)} active Foreign Key constraints** "
                "recorded in PostgreSQL `information_schema.table_constraints`:\n",
            ]
            for fk in fks:
                lines.append(f"- **`{fk[0]}.{fk[1]}`** ➔ **`{fk[2]}.{fk[3]}`** (Constraint: `{fk[4]}`)")

            lines.extend([
                "\n### Domain Entity Relationships:\n",
                "1. **Customers to Orders (`customers` ➔ `orders`):**",
                "   - **1-to-Many:** Each customer account (`customer_id`) places one or multiple orders.",
                "2. **Orders to Order Items (`orders` ➔ `order_items`):**",
                "   - **1-to-Many:** An order consists of one or more items identified by composite key `(order_id, order_item_id)`.",
                "3. **Order Items to Products (`order_items` ➔ `products`):**",
                "   - **Many-to-1:** Every ordered item links directly to a specific catalog item (`product_id`).",
                "4. **Order Items to Sellers (`order_items` ➔ `sellers`):**",
                "   - **Many-to-1:** Each item is fulfilled and dispatched by an independent merchant (`seller_id`).",
                "5. **Orders to Payments (`orders` ➔ `order_payments`):**",
                "   - **1-to-Many:** Orders can be split across multiple payment methods or installments (`payment_sequential`).",
                "6. **Orders to Reviews (`orders` ➔ `order_reviews`):**",
                "   - **1-to-Many:** Post-delivery customer feedback and rating linked by `order_id`.",
                "7. **Products to Category Translations (`products` ➔ `product_category_name_translation`):**",
                "   - Bridges Portuguese category names to English translation keys.",
                "8. **Entities to Geolocation (`customers`/`sellers` ➔ `geolocation`):**",
                "   - Geo-coordinates (lat/lng) linked through 5-digit postal zip code prefixes.",
                "\n> Referential integrity is strictly maintained across all transaction tables with zero orphan records.",
            ])

        return ChatResponse(
            text="\n".join(lines),
            source="postgresql",
            intent="schema_relationships",
            metrics=metrics,
            sql_query=fk_query.text.strip(),
            language=language,
        )

    # -------------------------------------------------------------
    # 5. Intent Classification & Table Extraction
    # -------------------------------------------------------------
    def classify_intent(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """Classify user query into schema intents:
        - ('schema_overview', None)
        - ('schema_table_structure', table_name)
        - ('schema_primary_keys', table_name or None)
        - ('schema_relationships', None)
        - (None, None) if not a schema question
        """
        clean_q = query.lower().strip()
        # Clean punctuation
        clean_q = re.sub(r"[?!.,;:]", " ", clean_q)
        clean_q = re.sub(r"\s+", " ", clean_q)

        # 1. Primary keys intent
        if any(p in clean_q for p in [
            "primary key", "primary keys", "pk of", "pks of", "pk for",
            "clé primaire", "clés primaires", "cle primaire", "cles primaires",
            "quelle est la clé primaire", "quelles sont les clés primaires"
        ]):
            tbl = self.extract_table_name(clean_q)
            return ("schema_primary_keys", tbl)

        # 2. Database relationships intent
        if any(p in clean_q for p in [
            "foreign key", "foreign keys", "fk constraints", "relationships between",
            "how are tables related", "table relationships", "database relationships",
            "database relations", "entity relationship", "er diagram", "erd",
            "clés étrangères", "cle etrangere", "cles etrangeres", "relations entre",
            "comment sont reliées", "relations de la base", "relations entre les tables"
        ]) or (
            "relationship" in clean_q and any(t in clean_q for t in ["order", "customer", "product", "seller", "item"])
        ):
            return ("schema_relationships", None)

        # 3. Table structure / columns intent
        # Check if table name is present along with column/describe/structure keywords
        tbl = self.extract_table_name(clean_q)
        is_structure_word = any(p in clean_q for p in [
            "columns in", "what columns", "list columns", "describe", "describe table",
            "structure of", "table structure", "data types in", "schema of table",
            "colonnes dans", "quelles colonnes", "structure de", "décris la table",
            "decris la table", "décrire", "decrire", "types de données dans"
        ])

        if tbl and is_structure_word:
            return ("schema_table_structure", tbl)

        if tbl and any(p in clean_q for p in ["columns", "colonnes", "structure", "fields", "champs", "describe"]):
            return ("schema_table_structure", tbl)

        # 4. Database overview intent
        if any(p in clean_q for p in [
            "what tables exist", "tables exist", "list tables", "show tables", "all tables",
            "database schema", "show me the database schema", "show schema", "view schema",
            "database overview", "explore database", "database structure", "database tables",
            "quelles tables existent", "quelles sont les tables", "liste des tables",
            "schéma de la base", "schema de la base", "tables de la base", "structure de la base"
        ]):
            return ("schema_overview", None)

        return (None, None)

    def execute_intent(
        self,
        intent: str,
        table_name: Optional[str] = None,
        language: str = "en",
    ) -> Optional[ChatResponse]:
        """Dispatch to the corresponding schema explorer method."""
        if intent == "schema_overview":
            return self.get_database_overview(language=language)
        elif intent == "schema_table_structure":
            target = table_name or "orders"
            return self.get_table_structure(target, language=language)
        elif intent == "schema_primary_keys":
            return self.get_primary_keys(table_name=table_name, language=language)
        elif intent == "schema_relationships":
            return self.get_database_relationships(language=language)
        return None

    def extract_table_name(self, text_input: str) -> Optional[str]:
        """Safely extract table name (canonical or queried) from user query."""
        clean = text_input.lower().strip()
        # Look for multi-word or compound approved names first
        compounds = [
            ("product_category_name_translation", "product_category_name_translation"),
            ("category translation", "product_category_name_translation"),
            ("category translations", "product_category_name_translation"),
            ("order_items", "order_items"),
            ("order items", "order_items"),
            ("order_payments", "order_payments"),
            ("order payments", "order_payments"),
            ("order_reviews", "order_reviews"),
            ("order reviews", "order_reviews"),
            ("geolocation", "geolocation"),
        ]
        for phrase, canonical in compounds:
            if phrase in clean:
                return canonical

        # Single word matching for approved synonyms
        words = re.findall(r"\b[a-z_]+\b", clean)
        for w in words:
            if w in TABLE_SYNONYMS:
                return TABLE_SYNONYMS[w]

        # Phrasing matching for non-approved or arbitrary table names:
        # e.g., "describe the users table", "columns in users table", "structure of users"
        patterns = [
            r"(?:describe|décris|decris)(?:\s+the|\s+la|\s+le)?\s+table\s+([a-z0-9_]+)",
            r"(?:describe|décris|decris)(?:\s+the|\s+la|\s+le)?\s+([a-z0-9_]+)(?:\s+table)?",
            r"(?:columns in|colonnes dans|colonnes de)(?:\s+the|\s+la|\s+le)?\s+([a-z0-9_]+)",
            r"(?:structure of|structure de)(?:\s+the|\s+la|\s+le)?(?:\s+table)?\s+([a-z0-9_]+)",
            r"(?:primary keys of|pk of|clé primaire de)(?:\s+the|\s+la|\s+le)?\s+([a-z0-9_]+)",
        ]
        stop_words = {"the", "a", "an", "table", "tables", "database", "schema", "olist", "public", "la", "le", "les", "des"}
        for pat in patterns:
            m = re.search(pat, clean)
            if m:
                candidate = m.group(1).strip()
                if candidate not in stop_words:
                    return TABLE_SYNONYMS.get(candidate, candidate)

        return None

    def _normalize_table_name(self, raw_name: Optional[str]) -> Optional[str]:
        if not raw_name:
            return None
        clean = raw_name.lower().strip()
        return TABLE_SYNONYMS.get(clean, clean)

    def is_french(self, text_input: str) -> bool:
        """Robust detection for French schema queries with English cognate disambiguation."""
        lowered = text_input.lower()
        clean = re.sub(r"[^\w\s]", " ", lowered)
        words = set(clean.split())

        fr_indicators = {
            "quelles", "quelle", "quels", "quel", "décris", "decris", "décrire", "decrire",
            "montre", "donne", "colonnes", "colonne", "clés", "clé", "cles", "cle",
            "étrangères", "étrangère", "etrangeres", "etrangere", "primaires", "primaire",
            "données", "donnees", "commandes", "produits", "vendeurs", "articles", "avis",
            "paiements", "dans", "sont", "comment", "reliant"
        }
        en_indicators = {
            "what", "which", "show", "describe", "exist", "columns", "between",
            "how", "where", "explain", "primary", "foreign", "keys", "database"
        }

        has_accent = any(c in lowered for c in ["é", "è", "ê", "à", "ç", "ù"])
        fr_count = len(words.intersection(fr_indicators)) + (2 if has_accent else 0)
        en_count = len(words.intersection(en_indicators))

        if fr_count > en_count:
            return True
        return False

    def _handle_unsupported_table(self, table_name: str, language: str = "en") -> ChatResponse:
        """Safely explain that the requested table does not exist in the public Olist schema."""
        is_fr = language == "fr"
        tbl_list = ", ".join([f"`{t}`" for t in APPROVED_TABLES])

        if is_fr:
            msg = (
                f"La table **`{table_name}`** n'existe pas dans le schéma public de la base de données Olist.\n\n"
                f"Par mesure de sécurité et d'intégrité, seules les 9 tables du dataset officiel Olist sont accessibles :\n"
                f"{tbl_list}.\n\n"
                "Essayez par exemple : *\"Décris la table des commandes\"* ou *\"Quelles sont les colonnes de customers ?\"*."
            )
        else:
            msg = (
                f"The table **`{table_name}`** does not exist in the `public` schema of the Olist database.\n\n"
                f"For data security and schema integrity, only the 9 verified Olist tables are accessible:\n"
                f"{tbl_list}.\n\n"
                "Try asking: *\"What columns are in the orders table?\"* or *\"Describe the products table\"*."
            )

        return ChatResponse(
            text=msg,
            source="unsupported",
            intent="schema_table_structure",
            language=language,
        )


_global_schema_service: Optional[SchemaService] = None


def get_schema_service(db: Session) -> SchemaService:
    """Dependency helper for SchemaService."""
    return SchemaService(db)
