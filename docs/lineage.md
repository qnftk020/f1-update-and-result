# 팀 계보 근거

이 문서는 `data/curated/lineage/`의 계보 테이블이 어떤 근거로 만들어졌는지 적는다. 계보는 2025 그리드 10개 팀의 조직 연속성을 사이트가 자체 정의한 것이며, 원자료의 `constructor_id`는 바꾸지 않는다.

- 확인일: 2026-11-11
- 초안의 출발점: F1DB `v2026.20.0`의 컨스트럭터 chronology (CC BY 4.0)
- 검증 방법: 연결 행마다 근거 페이지를 열어 아래 인용문이 실제로 있는지 대조했다. 근거 41건이 모두 대조를 통과했다(`lineage_evidence.csv`).
- 근거 우선순위: 팀 공식 사이트, formula1.com, fia.com, 영어 위키백과 순이다. 공식 사이트에 계보 서술이 없는 구간은 위키백과를 썼다.

## 읽는 법

- 연결 유형: 출발점(계보의 첫 팀), 명칭 변경(같은 조직의 이름만 바뀜), 인수(조직이 이어진 채 소유주가 바뀜), 참가권 인수(참가권만 넘어가고 조직은 새로 만들어짐).
- 같은 `constructor_id`라도 기간에 따라 다른 조직일 수 있다. 계보에 넣지 않은 구간은 각 절의 "제외 구간"에 적었다.
- 제외 구간의 근거는 대부분 간접 근거다. "두 팀이 다른 조직"이라고 직접 쓴 문장은 찾지 못했고, 철수 사실, 거점과 활동 기간의 차이, 이후 팀이 기존 팀을 인수해 만들어졌다는 서술로 판단했다.

## 마라넬로 (페라리)

- `lineage_id`: `maranello`, 거점: Maranello, Italy, 2025년 `constructor_id`: `ferrari`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 1950–2025 | `ferrari` | Ferrari | 출발점 | https://www.formula1.com/en/teams/ferrari | "competed in every season since the world championship began" |

## 워킹 (맥라렌)

- `lineage_id`: `woking`, 거점: Woking, United Kingdom, 2025년 `constructor_id`: `mclaren`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 1966–1970 | `mclaren-ford` | McLaren | 출발점 | https://www.mclaren.com/racing/heritage/bruce-mclaren/ | "took the marque into grand prix racing in 1966" |
| 1966 | `mclaren-seren` | McLaren | 출발점 | https://www.mclaren.com/racing/heritage/bruce-mclaren/ | "took the marque into grand prix racing in 1966" |
| 1967–1968 | `mclaren-brm` | McLaren | 출발점 | https://www.mclaren.com/racing/heritage/bruce-mclaren/ | "took the marque into grand prix racing in 1966" |
| 1970 | `mclaren-alfa_romeo` | McLaren | 출발점 | https://www.mclaren.com/racing/heritage/bruce-mclaren/ | "took the marque into grand prix racing in 1966" |
| 1968–2025 | `mclaren` | McLaren | 출발점 | https://www.mclaren.com/racing/heritage/bruce-mclaren/ | "took the marque into grand prix racing in 1966" |

- `mclaren-ford`: Jolpica는 초기 McLaren을 섀시-엔진 조합 ID로 나눈다.

## 그로브 (윌리엄스)

- `lineage_id`: `grove`, 거점: Grove, United Kingdom, 2025년 `constructor_id`: `williams`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 1978–2025 | `williams` | Williams | 출발점 | https://www.williamsf1.com/articles/d807f8a4-e045-4277-994e-f9a872101cfe/atlassian-williams-f1-team-our-journey | "debuted their first in-house car, the FW06, in 1978" |

- `williams`: 1975-1976년 williams는 Frank Williams Racing Cars(이후 Wolf)라 제외한다. 1977년은 고객용 March로 출전해 constructor_id가 march라서 연결하지 않는다.
- 제외 구간의 근거(`williams`): https://en.wikipedia.org/wiki/Frank_Williams_Racing_Cars "to set up Williams Grand Prix Engineering with Patrick Head in 1977"

## 브래클리 (메르세데스)

- `lineage_id`: `brackley`, 거점: Brackley, United Kingdom, 2025년 `constructor_id`: `mercedes`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 1970–1998 | `tyrrell` | Tyrrell | 출발점 | https://en.wikipedia.org/wiki/Tyrrell_Racing | "While BAR bought the Tyrrell F1 team and entry" |
| 1999–2005 | `bar` | BAR | 참가권 인수 | https://en.wikipedia.org/wiki/Tyrrell_Racing | "they used a different factory, chassis builder and engine" |
| 2006–2008 | `honda` | Honda | 인수 | https://en.wikipedia.org/wiki/British_American_Racing | "BAR Honda became Honda Racing F1 Team for the 2006 Formula One season" |
| 2009 | `brawn` | Brawn | 인수 | https://en.wikipedia.org/wiki/Brawn_GP | "management buyout led by Ross Brawn" |
| 2010–2025 | `mercedes` | Mercedes | 인수 | https://www.mercedesamgf1.com/news/growing-from-our-roots-how-mercedes-made-its-mark-on-f1 | "gone from BAR, BAR Honda, Honda, then Brawn" |

- `bar`: Tyrrell의 참가권을 인수해 브래클리에 새 조직을 세웠다.
- `honda`: 1964-1968년 honda는 별도의 Honda 워크스라 제외한다.
- `brawn`: Ross Brawn이 이끈 경영진 인수다.
- `mercedes`: 1954-1955년 mercedes는 별도의 Daimler-Benz 워크스라 제외한다.
- 제외 구간의 근거(`honda`): https://en.wikipedia.org/wiki/Honda_in_Formula_One "Honda purchased the remaining 55% share of BAR"
- 제외 구간의 근거(`mercedes`): https://www.mercedesamgf1.com/news/celebrating-the-first-decade-of-the-mercedes-f1-works-team "For the first time since 1955, a Mercedes works team was competing in Formula One again"

## 엔스톤 (알핀)

- `lineage_id`: `enstone`, 거점: Enstone, United Kingdom, 2025년 `constructor_id`: `alpine`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 1981–1985 | `toleman` | Toleman | 출발점 | https://en.wikipedia.org/wiki/Toleman | "It participated in Formula One between 1981 and 1985" |
| 1986–2001 | `benetton` | Benetton | 인수 | https://en.wikipedia.org/wiki/Benetton_Formula | "when the Toleman team was sold to the Benetton family" |
| 2002–2011 | `renault` | Renault | 인수 | https://en.wikipedia.org/wiki/Benetton_Formula | "the team was fully re-branded as the Renault F1 Team for the 2002 season" |
| 2012–2015 | `lotus_f1` | Lotus F1 | 명칭 변경 | https://en.wikipedia.org/wiki/Lotus_F1_Team | "The team competed under the Lotus name from 2012 until 2015" |
| 2016–2020 | `renault` | Renault | 인수 | https://en.wikipedia.org/wiki/Renault_in_Formula_One | "Renault announced that they had purchased the Lotus F1 Team" |
| 2021–2025 | `alpine` | Alpine | 명칭 변경 | https://en.wikipedia.org/wiki/Team_Enstone | "Renault renamed the team to the Alpine F1 Team" |

- `renault`: 1977-1985년 renault는 별도의 Renault 워크스라 제외한다.
- 제외 구간의 근거(`renault`): https://en.wikipedia.org/wiki/Renault_in_Formula_One "it withdrew at the end of 1985"

## 밀턴킨스 (레드불)

- `lineage_id`: `milton_keynes`, 거점: Milton Keynes, United Kingdom, 2025년 `constructor_id`: `red_bull`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 1997–1999 | `stewart` | Stewart | 출발점 | https://en.wikipedia.org/wiki/Red_Bull_Racing | "traces its origins back to the Stewart Grand Prix outfit that made its debut in 1997" |
| 2000–2004 | `jaguar` | Jaguar | 인수 | https://en.wikipedia.org/wiki/Jaguar_Racing_(Formula_One) | "The team operated for five seasons, from 2000 to 2004" |
| 2005–2025 | `red_bull` | Red Bull | 인수 | https://en.wikipedia.org/wiki/Red_Bull_Racing | "agreed its purchase of Jaguar Racing" |

## 파엔차 (레이싱 불스)

- `lineage_id`: `faenza`, 거점: Faenza, Italy, 2025년 `constructor_id`: `rb`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 1985–2005 | `minardi` | Minardi | 출발점 | https://en.wikipedia.org/wiki/Minardi | "It competed in the Formula One World Championship from 1985 until 2005" |
| 2006–2019 | `toro_rosso` | Toro Rosso | 인수 | https://en.wikipedia.org/wiki/Minardi | "the team was renamed Scuderia Toro Rosso for the 2006 season" |
| 2020–2023 | `alphatauri` | AlphaTauri | 명칭 변경 | https://en.wikipedia.org/wiki/Racing_Bulls | "Scuderia AlphaTauri from 2020 to 2023" |
| 2024 | `rb` | RB | 명칭 변경 | https://en.wikipedia.org/wiki/Racing_Bulls | "Visa Cash App RB F1 Team for the 2024 season" |
| 2025 | `rb` | Racing Bulls | 명칭 변경 | https://en.wikipedia.org/wiki/Racing_Bulls | "Racing Bulls in 2025" |

- `rb`: Jolpica는 2025년에도 rb를 쓴다.

## 힌빌 (자우버)

- `lineage_id`: `hinwil`, 거점: Hinwil, Switzerland, 2025년 `constructor_id`: `sauber`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 1993–2005 | `sauber` | Sauber | 출발점 | https://www.formula1.com/en/teams/kick-sauber | "into F1 in 1993" |
| 2006–2009 | `bmw_sauber` | BMW Sauber | 인수 | https://en.wikipedia.org/wiki/Sauber_Motorsport | "raced as BMW Sauber F1 Team from 2006 to 2009" |
| 2010–2018 | `sauber` | Sauber | 인수 | https://en.wikipedia.org/wiki/Sauber_Motorsport | "BMW sold its part back to Peter Sauber after the end of the 2009 season" |
| 2019–2023 | `alfa` | Alfa Romeo | 명칭 변경 | https://en.wikipedia.org/wiki/Sauber_Motorsport | "until 2023" |
| 2024–2025 | `sauber` | Kick Sauber | 명칭 변경 | https://www.formula1.com/en/latest/article/sauber-new-team-name-stake-f1-team-kick-alfa-romeo.3ExVqWTCT8pd7MEd71V5DK | "rebranding as Audi in 2026" |

- `sauber`: 2010년 참가 명칭은 BMW Sauber F1 Team이었다. F1DB chronology는 bmw-sauber를 2010년까지로 적지만 시즌 엔트런트 표는 2010년을 sauber로 적는다.
- `alfa`: 1950-1985년 alfa는 별도의 Alfa Romeo 워크스라 제외한다.
- 제외 구간의 근거(`alfa`): https://en.wikipedia.org/wiki/Alfa_Romeo_in_Formula_One "Alfa Romeo itself had no technical involvement with the team"

## 실버스톤 (애스턴 마틴)

- `lineage_id`: `silverstone`, 거점: Silverstone, United Kingdom, 2025년 `constructor_id`: `aston_martin`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 1991–2005 | `jordan` | Jordan | 출발점 | https://en.wikipedia.org/wiki/Jordan_Grand_Prix | "Jordan Grand Prix was a Formula One constructor that competed from 1991 to 2005" |
| 2006 | `mf1` | Midland | 인수 | https://en.wikipedia.org/wiki/Jordan_Grand_Prix | "before renaming the team as Midland F1 Racing for the 2006 season" |
| 2006 | `spyker_mf1` | Spyker MF1 | 인수 | https://en.wikipedia.org/wiki/Spyker_F1 | "before being sold to Spyker Cars towards the end of the 2006 season" |
| 2007 | `spyker` | Spyker | 명칭 변경 | https://en.wikipedia.org/wiki/Spyker_F1 | "before being sold to Spyker Cars towards the end of the 2006 season" |
| 2008–2018 | `force_india` | Force India | 인수 | https://en.wikipedia.org/wiki/Spyker_F1 | "The team was renamed Force India for the 2008 season" |
| 2019–2020 | `racing_point` | Racing Point | 인수 | https://www.fia.com/news/fia-approves-mid-season-entry-racing-point-force-india | "mid-season entry of Racing Point Force India" |
| 2021–2025 | `aston_martin` | Aston Martin | 명칭 변경 | https://en.wikipedia.org/wiki/Racing_Point_F1_Team | "The team rebranded to Aston Martin for the 2021 Formula One season" |

- `spyker_mf1`: 2006년 시즌 막바지에 Spyker가 인수해 이름을 바꿨다.
- `force_india`: 2018년 중반 이후의 Racing Point Force India도 Jolpica에서는 force_india다.
- `racing_point`: 2018년 8월 Racing Point UK가 자산을 인수했고 FIA는 기존 참가권을 제외한 뒤 새 참가권을 승인했다. 조직과 공장은 이어졌다.
- `aston_martin`: 1959-1960년 aston_martin은 별도 조직이라 제외한다.
- 제외 구간의 근거(`aston_martin`): https://www.astonmartinf1.com/en-GB/heritage "leading Aston Martin to exit Formula One in 1960"

## 캐나폴리스 (하스)

- `lineage_id`: `kannapolis`, 거점: Kannapolis, United States, 2025년 `constructor_id`: `haas`

| 기간 | `constructor_id` | 팀 | 연결 유형 | 근거 | 인용 |
|---|---|---|---|---|---|
| 2016–2025 | `haas` | Haas | 출발점 | https://www.haasf1team.com/season/team/gene-haas | "was granted a license by the" |

## 판단이 갈릴 수 있는 지점

- 브래클리 계보의 Tyrrell: BAR는 Tyrrell의 팀과 참가권을 샀지만 공장, 섀시 제작사, 엔진이 모두 달랐다. 메르세데스 공식 글은 BAR부터 헤아리고 Tyrrell을 언급하지 않는다. formula1.com 팀 정보는 첫 참가 연도를 1970년(Tyrrell)으로 적는다. 여기서는 Tyrrell을 포함하되 연결 유형을 "참가권 인수"로 구분했다. 화면에서 조직 기준으로 볼 때는 1999년부터로 끊을 수 있다.
- 실버스톤 계보의 2018년: 자산 매각과 새 참가권 승인으로 이어졌으므로 참가권 기준으로는 끊긴다. 조직과 공장이 이어져 계보에 포함했다. formula1.com 팀 정보는 첫 참가 연도를 2018년으로 적는다.
- 그로브 계보의 시작: 윌리엄스 공식 글은 Frank Williams Racing Cars를 사실상의 전신이라고 부른다. 그 회사는 Walter Wolf에게 넘어가 Walter Wolf Racing이 됐고 Williams Grand Prix Engineering은 1977년에 새로 세워졌으므로 계보에서 뺐다. 1977년은 고객용 March로 출전해 `constructor_id`가 `march`라서 연결하지 못했다.
- 엔스톤 계보: 위키백과 Team Enstone 문서는 현재 팀이 이전 팀들의 역사를 이어받는지에 대해 출처마다 견해가 다르다고 적는다.
- formula1.com 팀 페이지는 2026 시즌 정보로 바뀌어 있어 2025년 PU 공급사의 근거로 쓰지 않았다.

## PU 공급사 (2025년)

`constructor_seasons.parquet`의 `pu_manufacturer_id`는 F1DB 시즌 엔트런트에서 가져온다. 2025년 값은 FIA 미디어 키트의 참가 목록과 같다.

| 팀 | PU |
|---|---|
| McLaren, Mercedes, Williams, Aston Martin | Mercedes |
| Ferrari, Haas, Kick Sauber | Ferrari |
| Red Bull, Racing Bulls | Honda RBPT |
| Alpine | Renault |

- 근거: https://www.fia.com/sites/default/files/media_kit-2025_abu_dhabi_gp.pdf (참가 목록, 조사 단계에서 확인했고 인용문 자동 대조 대상에는 넣지 않았다)
