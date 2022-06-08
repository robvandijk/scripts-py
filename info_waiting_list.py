import src.xxapi_extended as xxapi
import os

def main():
    write_waiting_list = os.environ.get("WRITE_WAITING_LIST")
    # Connect to chain
    xxchain = xxapi.XXNetworkInterfaceExtended(url = "ws://localhost:63007", staking_verbose = False,
      write_waiting_list = write_waiting_list)

    if xxchain is None:
        exit(1)

    xxchain.info_waiting_list()


if __name__ == "__main__":
    main()
