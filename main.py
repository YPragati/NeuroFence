from security.sandbox import run_sandbox


def main():
    print("===================================")
    print("        NeuroFence AI Sandbox")
    print("===================================")

    prompt = input("\nEnter a prompt: ")

    print("\nRunning model...\n")

    response = run_sandbox(prompt)

    print("Response:")
    print(response)


if __name__ == "__main__":
    main()