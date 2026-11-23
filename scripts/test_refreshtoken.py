from app.core.security import (
    generate_refresh_token,
    hash_refresh_token,
)


def test_refresh_token_generation():
    token = generate_refresh_token()

    assert isinstance(token, str)
    assert len(token) > 30

    print("PASS: Refresh token generated")


def test_refresh_token_hashing():
    token = generate_refresh_token()

    hashed_token = hash_refresh_token(token)

    assert hashed_token != token
    assert len(hashed_token) == 64

    print("PASS: Refresh token hashed")


def test_hash_consistency():
    token = generate_refresh_token()

    first_hash = hash_refresh_token(token)
    second_hash = hash_refresh_token(token)

    assert first_hash == second_hash

    print("PASS: Hash consistency")


def test_different_tokens():
    token_one = generate_refresh_token()
    token_two = generate_refresh_token()

    assert token_one != token_two

    assert (
        hash_refresh_token(token_one)
        != hash_refresh_token(token_two)
    )

    print("PASS: Different tokens produce different hashes")


if __name__ == "__main__":
    test_refresh_token_generation()
    test_refresh_token_hashing()
    test_hash_consistency()
    test_different_tokens()

    print("\nAll refresh-token checks passed.")