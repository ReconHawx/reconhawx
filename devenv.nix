{
  pkgs,
  lib,
  config,
  inputs,
  ...
}: {
  git-hooks.enable = false;
  languages.python = {
    enable = true;
    version = "3.14";
    venv = {
      enable = true;
      requirements = ./requirements.txt;
    };
  };

  # https://devenv.sh/packages/
  packages = with pkgs; [
    zlib.dev
    kubectl
    minikube
    kubernetes-helm
    nginx
    nodejs
    docker
    docker-compose
    lsof
    postgresql
    openssl
    process-compose
    k9s
    trufflehog
    secretspec
    grype
    gh
    tesseract
    katana
    httpx
  ];
  env = {};
  processes = {};
  services = {};
  scripts = {};
}
