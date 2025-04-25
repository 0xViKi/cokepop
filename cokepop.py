import hashlib
import binascii
import argparse
import os
import sys
import concurrent.futures
from tqdm import tqdm
from itertools import islice
from math import ceil

# File to cache cracked passwords for future use
POT_FILE = ".cokepop.pot"

# ANSI escape codes for colored terminal output
GREEN = "\033[92m"
RED = '\033[91m'
END = "\033[0m"

def chunks(iterable, size):
    """
    Yield successive chunks from an iterable of the specified size.
    This is useful for processing large lists in smaller, manageable parts.
    """
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk

def pbkdf2_hash(password, salt, iterations, dklen):
    """
    Generates a PBKDF2-SHA256 hash of the given password using the provided salt,
    iteration count, and desired derived key length.
    """
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations,
        dklen
    )

def check_password(password, targetHashBytes, targetSaltBytes, iterations, dklen):
    """
    Checks if the given password, when hashed with the provided salt, iterations,
    and derived key length, matches the target hash.
    Returns the password if it matches, otherwise returns None.
    """
    hashBytes = pbkdf2_hash(password, targetSaltBytes, iterations, dklen)
    if hashBytes == targetHashBytes:
        return password
    return None

def find_matching_password(wordlist, targetHash, targetSalt, iterations, dklen, chunksize, cpuCount):
    """
    Reads a wordlist, divides it into chunks, and uses multiple processes to check
    each password in the chunks against the target hash.

    Args:
        wordlist (str): Path to the wordlist file.
        targetHash (str): The target password hash in hexadecimal format.
        targetSalt (str): The salt used to generate the hash in hexadecimal format.
        iterations (int): The number of iterations used in the PBKDF2-SHA256 hashing.
        dklen (int): The derived key length used in the PBKDF2-SHA256 hashing.
        chunksize (int): The number of passwords to process in each chunk.
        cpu_count (int): The number of CPU processes to use for parallel processing.

    Returns:
        tuple or None: If a matching password is found, returns a tuple containing
                       the cracked password (str) and the index of the chunk where
                       it was found (int). Returns None if no match is found.
    """
    targetHashBytes = binascii.unhexlify(targetHash)
    targetSaltBytes = binascii.unhexlify(targetSalt)

    try:
        with open(wordlist, 'r', encoding='utf-8', errors='ignore') as f:
            passwords = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"{RED}[ERROR] Wordlist file not found: {wordlist}{END}")
        sys.exit(1)

    totalPwds = len(passwords)
    totalChunks = (totalPwds + chunksize - 1) // chunksize

    print("-" * 50)
    print(f"[+] Using {cpuCount} processes with chunk size {chunksize}...")
    print(f"[+] Total Passwords: {totalPwds} ({totalChunks} chunks)")
    print("-" * 50)

    with tqdm(total=totalChunks, desc="🧠 Cracking Chunks", ncols=90, unit=" chunk") as chunkProgressbar:
        for chunkIndex, pwdChunk in enumerate(chunks(passwords, chunksize), 1):
            with tqdm(total=len(pwdChunk), desc=f"🔐 Passwd in chunk {chunkIndex}", ncols=90, leave=False, unit=" passwd") as pwdProgressbar:
                with concurrent.futures.ProcessPoolExecutor(max_workers=cpuCount) as executor:
                    futures = {
                        executor.submit(check_password, pwd, targetHashBytes, targetSaltBytes, iterations, dklen): pwd
                        for pwd in pwdChunk
                    }

                    for future in concurrent.futures.as_completed(futures):
                        result = future.result()
                        pwdProgressbar.update(1)

                        if result is not None:
                            executor.shutdown(wait=False, cancel_futures=True)
                            return result, chunkIndex

            chunkProgressbar.update(1)

    return None


def check_potfile(targetHash):
    """
    Checks if the target hash exists in the pot file (cache of cracked passwords).
    Returns the cracked password if found, otherwise returns None.
    """
    if not os.path.exists(POT_FILE):
        return None
    with open(POT_FILE, "r", encoding="utf-8") as pot:
        for line in pot:
            try:
                savedHash, password = line.strip().split(":", 1)
                if savedHash.lower() == targetHash.lower():
                    return password
            except ValueError:
                continue
    return None


def save_to_potfile(targetHash, password):
    """
    Saves the cracked password and its corresponding hash to the pot file.
    """
    with open(POT_FILE, "a", encoding="utf-8") as pot:
        pot.write(f"{targetHash}:{password}\n")


def print_banner():
    """
    Prints a colorful ASCII banner to the console.
    """
    asciiBanner = r"""
  ██████╗ ██████╗ ██╗  ██╗███████╗██████╗  ██████╗ ██████╗
 ██╔════╝██╔═══██╗██║ ██╔╝██╔════╝██╔══██╗██╔═══██╗██╔══██╗
 ██║     ██║   ██║█████╔╝ █████╗  ██████╔╝██║   ██║██████╔╝
 ██║     ██║   ██║██╔═██╗ ██╔══╝  ██╔═══╝ ██║   ██║██╔═══╝
 ╚██████╗╚██████╔╝██║  ██╗███████╗██║     ╚██████╔╝██║
  ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝      ╚═════╝ ╚═╝
"""
    taglineBanner = r"""[🔐] PBKDF2-SHA256 Cracker - Terminal Edition"""
    print(f"{GREEN}{asciiBanner.center(50)}{END}")  # Green text using ANSI escape code
    print(f"{RED}{taglineBanner.center(50)}{END}")  # Red text using ANSI escape code
    print()

def main():
    """
    Main function to parse arguments, check the pot file, initiate the password
    cracking process, and display the results.
    """
    print_banner()

    parser = argparse.ArgumentParser(description="PBKDF2-SHA256 Password cracker using concurrent.futures")
    parser.add_argument("-w", "--wordlist", type=str, required=True, help="Path to wordlist")
    parser.add_argument("-s", "--salt", type=str, required=True, help="Salt (hex format)")
    parser.add_argument("-p", "--passwd-hash", type=str, required=True, help="Password hash (hex format)", dest="passwdHash")
    parser.add_argument("-i", "--iterations", type=int, default=50000, help="Iterations (default: 50000)")
    parser.add_argument("-c", "--cpu", type=int, default=os.cpu_count(), help="Number of CPU processes (default: max)")
    parser.add_argument("-S", "--chunk-size", type=int, default=100, help="Chunk size (default: 100)", dest="chunkSize")
    parser.add_argument("-d", "--dklen", type=int, default=50, help="Derived key length (default: 50)")

    args = parser.parse_args(args=None if sys.argv[1:] else ['--help'])

    print("-" * 50)
    print(f"[🔍] Checking .pot file for hash...")
    cachedPass = check_potfile(args.passwdHash)
    if cachedPass:
        print("-" * 50)
        print(f"{GREEN}[✅] Password found in pot file: {cachedPass}{END}")
        print("-" * 50)
        return

    result, chunkIndex = find_matching_password(
        wordlist=args.wordlist,
        targetHash=args.passwdHash,
        targetSalt=args.salt,
        iterations=args.iterations,
        dklen=args.dklen,
        chunksize=args.chunkSize,
        cpuCount=args.cpu
    )

    if result is not None:
        print()
        print("-" * 50)
        print(f"{GREEN}[✅] Password found in chunk {chunkIndex}{END}")
        print(f"{GREEN}[✅] Cracked Password: {result} {END}")
        print("-" * 50)
        save_to_potfile(args.passwdHash, result)
    else:
        print()
        print("-" * 50)
        print(f"{RED}[❎] Password not found {END}")
        print("-" * 50)

if __name__ == '__main__':
    main()