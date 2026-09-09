from security.sandbox import run_sandbox


def main():
    print("===================================")
    print("        NeuroFence AI Sandbox")
    print("===================================")

    prompt = input("\nEnter a prompt: ")

    print("\nRunning model...\n")

    result = run_sandbox(prompt)

    security = result["security"]
    decision = result["decision"]

    print("Security Analysis:")
    print(f"Status : {security['status']}")
    print(f"Score  : {security['score']}")

    print("\nSecurity Decision:")
    print(f"Action : {decision['action']}")

    print("\nResponse:")
    print(result["response"])


if __name__ == "__main__":
    main()