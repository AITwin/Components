import os
import random


def get_all_tokens(key_name: str) -> list[str]:
    keys = [os.environ[key_name]]
    i = 1
    while f"{key_name}_{i}" in os.environ:
        keys.append(os.environ[f"{key_name}_{i}"])
        i += 1
    return keys


def get_random_token(key_name: str) -> str:
    return random.choice(get_all_tokens(key_name))
