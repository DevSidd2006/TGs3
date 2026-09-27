from pathlib import Path


def test_env_example_documents_blockchain_demo_settings():
    env = Path(".env.example").read_text()

    for name in (
        "BLOCKCHAIN_ENABLED",
        "BLOCKCHAIN_RPC_URL",
        "BLOCKCHAIN_CONTRACT_ADDRESS",
        "BLOCKCHAIN_CHAIN_ID",
        "BLOCKCHAIN_ABI_PATH",
        "ENCRYPTION_MASTER_KEY",
    ):
        assert f"{name}=" in env


def test_local_chain_scripts_are_documented_and_present():
    readme = Path("README.md").read_text()

    assert "scripts/start_local_chain.sh" in readme
    assert "scripts/deploy_contract.sh" in readme
    assert Path("scripts/start_local_chain.sh").exists()
    assert Path("scripts/deploy_contract.sh").exists()
