{
  description = "ingenuity-elodin development tools; Elodin binaries are supplied separately";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/34268251cf5547d39063f2c5ea9a196246f7f3a6";
  outputs = { self, nixpkgs }:
    let systems = [ "aarch64-darwin" "x86_64-darwin" "aarch64-linux" "x86_64-linux" ];
    in {
      devShells = nixpkgs.lib.genAttrs systems (system:
        let pkgs = import nixpkgs { inherit system; }; in {
          default = pkgs.mkShell {
            packages = with pkgs; [ uv python3 ruff curl rsync openssh git git-lfs nodejs_22 ];
          };
        });
    };
}
