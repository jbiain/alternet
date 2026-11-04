# Installing Alternet

Needs Python 3.9+.

    pip install -e core/            # from the project source, installs `alternet` and Reticulum
    alternet init --no-auto --standalone
    alternet publish <directory> --name <name>
    alternet node                   # announce and serve while this runs

On a phone without a package manager (tested with a-Shell on iOS):

    pip install --no-deps rns
    python -m alternet init --no-auto --standalone
    python -m alternet connect <host>:4242
    python -m alternet read <site-id> --wait 20

To join the public relay so you're reachable across networks:

    alternet connect 178.128.165.25:4242
