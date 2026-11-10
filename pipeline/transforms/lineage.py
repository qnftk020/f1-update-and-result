"""팀 계보 연결. (T3)

원자료의 constructor_id는 브랜드 단위라 서로 다른 조직이 섞여 있다. 계보는 사람이 큐레이션한
data/curated/lineage/lineage_links.csv 의 (constructor_id, 시즌 구간) 으로만 연결한다.

실행: uv run python -m pipeline.transforms.lineage
"""

from __future__ import annotations

import duckdb

from pipeline.config import CURATED_DIR

LINEAGE_DIR = CURATED_DIR / "lineage"
LINKS = LINEAGE_DIR / "lineage_links.csv"
LINEAGES = LINEAGE_DIR / "lineages.csv"

LINKS_SQL = f"""
    select lineage_id, constructor_id, season_from::int as season_from,
           season_to::int as season_to, f1db_constructor_id, team_name, link_type
    from read_csv('{LINKS}', header = true, all_varchar = true)
"""


def build() -> int:
    """시즌별 (constructor_id -> lineage_id, PU 제조사) 테이블을 만든다.

    결과에 한 번이라도 나온 모든 (시즌, constructor_id)를 싣는다. 2025 그리드 계보에 속하지 않는
    팀은 lineage_id가 비어 있다. PU 제조사는 F1DB 시즌 엔트런트에서 가져온다.
    """
    con = duckdb.connect()
    out = LINEAGE_DIR / "constructor_seasons.parquet"
    con.execute(f"""
        copy (
            with links as ({LINKS_SQL}),
            seen as (
                select distinct season, constructor_id
                from '{CURATED_DIR}/jolpica/results.parquet'
            ),
            pu as (
                select season, f1db_constructor_id,
                       string_agg(distinct engine_manufacturer_id, '|'
                                  order by engine_manufacturer_id) as pu_manufacturer_id,
                       string_agg(distinct entrant_name, ' | ' order by entrant_name)
                           as entrant_name
                from '{CURATED_DIR}/f1db/season_entrants.parquet' group by 1, 2
            )
            select s.season, s.constructor_id, l.lineage_id, l.f1db_constructor_id,
                   l.team_name, pu.entrant_name, pu.pu_manufacturer_id
            from seen s
            left join links l on l.constructor_id = s.constructor_id
                             and s.season between l.season_from and l.season_to
            left join pu on pu.season = s.season
                        and pu.f1db_constructor_id = l.f1db_constructor_id
            order by s.season, s.constructor_id
        ) to '{out}' (format parquet, compression zstd)
    """)
    return con.execute(f"select count(*) from '{out}'").fetchone()[0]


if __name__ == "__main__":
    print(f"lineage/constructor_seasons: {build()} rows")
