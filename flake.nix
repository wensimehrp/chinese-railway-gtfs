{
  description = "chinese-railway-gtfs development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          # MongoDB is SSPL-licensed, which nixpkgs marks unfree. Allowing it
          # here keeps the dev shell self-contained (no system configuration).
          config.allowUnfree = true;
        };

        # railgo-parser needs a local MongoDB on 127.0.0.1:27017. nixpkgs'
        # `mongodb` compiles the server from source (it is unfree, so it is not
        # in the binary cache), which takes hours. Package MongoDB's official
        # prebuilt Linux binary instead -- fetched and patched, never compiled.
        # Shared-library deps (from `readelf -d bin/mongod`): libcurl, libssl/
        # libcrypto, libgcc_s, plus glibc.
        mongodb = pkgs.stdenv.mkDerivation rec {
          pname = "mongodb";
          version = "7.0.43";

          src = pkgs.fetchurl {
            url = "https://fastdl.mongodb.org/linux/mongodb-linux-x86_64-ubuntu2204-${version}.tgz";
            hash = "sha256-y6hLR5MuvN0JPeN/L9u71BURbSEYfM+RF1aHJoWdb4E=";
          };

          nativeBuildInputs = [ pkgs.autoPatchelfHook ];
          buildInputs = [
            pkgs.curl
            pkgs.openssl
            pkgs.stdenv.cc.cc.lib
          ];

          dontConfigure = true;
          dontBuild = true;

          installPhase = ''
            runHook preInstall
            mkdir -p $out
            cp -r bin $out/
            cp README LICENSE-Community.txt THIRD-PARTY-NOTICES $out/ 2>/dev/null || true
            runHook postInstall
          '';

          meta = {
            description = "MongoDB Community Server (official prebuilt binary)";
            homepage = "https://www.mongodb.com/";
            license = pkgs.lib.licenses.unfreeRedistributable;
            platforms = [ "x86_64-linux" ];
            mainProgram = "mongod";
          };
        };

        railgo-mongod = pkgs.writeShellApplication {
          name = "railgo-mongod";
          runtimeInputs = [
            mongodb
            pkgs.coreutils
          ];
          text = ''
            dbpath="''${RAILGO_MONGODB_DIR:-$PWD/.mongodb}"
            port="''${RAILGO_MONGODB_PORT:-27017}"
            mkdir -p "$dbpath"
            echo "MongoDB listening on 127.0.0.1:$port (data in $dbpath)" >&2
            exec mongod --dbpath "$dbpath" --bind_ip 127.0.0.1 --port "$port" "$@"
          '';
        };

        isX86Linux = pkgs.stdenv.hostPlatform.system == "x86_64-linux";
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            pkgs.uv # Python project / dependency management
            pkgs.typst # document tooling
          ]
          ++ pkgs.lib.optionals isX86Linux [
            mongodb # the prebuilt server (provides `mongod`)
            pkgs.mongosh # shell for inspecting the database
            railgo-mongod # helper that starts a local mongod
          ];
        };
      }
    );
}
