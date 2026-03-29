import uvicorn


def main() -> None:
    uvicorn.run("onx.api.app:app", host="127.0.0.1", port=8081, reload=True)


if __name__ == "__main__":
    main()
