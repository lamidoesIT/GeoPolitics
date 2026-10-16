from models.domain_models import PopulationCalculator

RAW_WORLDOMETER_COUNTRIES = [
    ("India", 1_450_935_791),          # > 150M -> 9 soldiers
    ("United States", 345_426_571),    # > 150M -> 9 soldiers
    ("Nigeria", 232_679_478),          # > 150M -> 9 soldiers
    ("Brazil", 211_998_573),           # > 150M -> 9 soldiers
    ("Russia", 144_820_423),           # 125M - 150M -> 8 soldiers
    ("Mexico", 130_861_007),           # 125M - 150M -> 8 soldiers
    ("Japan", 123_753_041),            # 100M - 125M -> 7 soldiers
    ("Philippines", 115_843_670),      # 100M - 125M -> 7 soldiers
    ("Egypt", 116_538_258),            # 100M - 125M -> 7 soldiers
    ("Vietnam", 100_987_686),          # 100M - 125M -> 7 soldiers
    ("Germany", 84_552_242),           # 75M - 100M -> 6 soldiers
    ("Turkey", 87_473_805),            # 75M - 100M -> 6 soldiers
    ("United Kingdom", 69_138_192),    # 50M - 75M -> 5 soldiers
    ("South Africa", 64_007_187),      # 50M - 75M -> 5 soldiers
    ("France", 66_548_530),            # 50M - 75M -> 5 soldiers
    ("Kenya", 56_432_944),             # 50M - 75M -> 5 soldiers
    ("Spain", 47_910_526),             # 25M - 50M -> 4 soldiers
    ("Argentina", 45_696_159),         # 25M - 50M -> 4 soldiers
    ("Canada", 39_742_430),            # 25M - 50M -> 4 soldiers
    ("Morocco", 38_081_173),           # 25M - 50M -> 4 soldiers
    ("Australia", 26_713_205),         # 25M - 50M -> 4 soldiers
    ("Netherlands", 18_228_742),       # 10M - 25M -> 3 soldiers
    ("Zimbabwe", 16_634_373),          # 10M - 25M -> 3 soldiers
    ("Portugal", 10_425_292),          # 10M - 25M -> 3 soldiers
    ("Sweden", 10_606_999),            # 10M - 25M -> 3 soldiers
    ("Switzerland", 8_921_981),        # 5M - 10M -> 2 soldiers
    ("Singapore", 5_832_387),          # 5M - 10M -> 2 soldiers
    ("New Zealand", 5_213_944),        # 5M - 10M -> 2 soldiers
    ("Namibia", 3_030_131),            # <= 5M -> 1 soldier
    ("Botswana", 2_521_139),           # <= 5M -> 1 soldier
    ("Iceland", 393_396),              # <= 5M -> 1 soldier
    ("Vatican City", 496)              # <= 5M -> 1 soldier
]

WORLD_COUNTRIES_SEED = [
    {
        "name": name,
        "population": pop,
        "base_soldiers": PopulationCalculator.calculate_soldiers(pop)
    }
    for name, pop in RAW_WORLDOMETER_COUNTRIES
]