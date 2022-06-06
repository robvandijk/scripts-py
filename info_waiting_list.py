import src.xxapi_extended as xxapi

def main():
    # Connect to chain
    xxchain = xxapi.XXNetworkInterfaceExtended(url="ws://localhost:63007",staking_verbose=False)

    if xxchain is None:
        exit(1)

    xxchain.info_waiting_list()


if __name__ == "__main__":
    main()
