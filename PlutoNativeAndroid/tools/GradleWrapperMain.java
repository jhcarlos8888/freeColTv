package org.gradle.wrapper;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.Properties;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Small bootstrapper for the official Gradle distribution; not Gradle's vendor wrapper implementation. */
public final class GradleWrapperMain {
    public static void main(String[] args) throws Exception {
        Path project = Paths.get(System.getProperty("user.dir")).toAbsolutePath().normalize();
        Path propertiesFile = project.resolve("gradle/wrapper/gradle-wrapper.properties");
        if (!Files.isRegularFile(propertiesFile)) {
            System.err.println("No se encontró gradle/wrapper/gradle-wrapper.properties en " + project);
            System.exit(2);
        }
        Properties properties = new Properties();
        try (InputStream in = Files.newInputStream(propertiesFile)) {
            properties.load(in);
        }
        String distributionUrl = properties.getProperty("distributionUrl", "").replace("\\:", ":");
        if (distributionUrl.isEmpty()) throw new IOException("distributionUrl no está configurado");
        String fileName = Paths.get(new URL(distributionUrl).getPath()).getFileName().toString();
        String versionFolder = fileName.replaceFirst("-bin\\.zip$", "").replaceFirst("-all\\.zip$", "");
        String userGradleHome = System.getenv("GRADLE_USER_HOME");
        Path home = (userGradleHome == null || userGradleHome.isEmpty())
                ? Paths.get(System.getProperty("user.home"), ".gradle") : Paths.get(userGradleHome);
        Path cache = home.resolve("wrapper/dists/pluto-native-bootstrap").resolve(versionFolder);
        Path gradleHome = cache.resolve(versionFolder);
        String executableName = isWindows() ? "gradle.bat" : "gradle";
        Path executable = gradleHome.resolve("bin").resolve(executableName);

        if (!Files.isRegularFile(executable)) {
            Files.createDirectories(cache);
            Path archive = cache.resolve(fileName);
            if (!Files.isRegularFile(archive) || Files.size(archive) == 0) download(distributionUrl, archive);
            extract(archive, cache);
            if (!Files.isRegularFile(executable)) {
                throw new IOException("La distribución descargada no contiene " + executable + ". Borra " + cache + " y reintenta.");
            }
            if (!isWindows()) executable.toFile().setExecutable(true);
        }

        java.util.List<String> command = new java.util.ArrayList<>();
        command.add(executable.toString());
        command.addAll(java.util.Arrays.asList(args));
        ProcessBuilder builder = new ProcessBuilder(command).directory(project.toFile()).inheritIO();
        builder.environment().putIfAbsent("JAVA_HOME", System.getProperty("java.home"));
        Process process = builder.start();
        int exitCode = process.waitFor();
        System.exit(exitCode);
    }

    private static void download(String address, Path destination) throws IOException {
        System.out.println("Descargando distribución oficial de Gradle desde services.gradle.org...");
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection();
        connection.setInstanceFollowRedirects(true);
        connection.setConnectTimeout(30000);
        connection.setReadTimeout(600000);
        connection.setRequestProperty("User-Agent", "PlutoNativeAndroid-GradleBootstrap/1.0");
        try {
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IOException("No se pudo descargar Gradle (HTTP " + status + ")");
            try (InputStream in = connection.getInputStream()) {
                Files.copy(in, destination, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            connection.disconnect();
        }
    }

    private static void extract(Path archive, Path destination) throws IOException {
        System.out.println("Preparando Gradle en " + destination + "...");
        try (ZipInputStream zip = new ZipInputStream(Files.newInputStream(archive))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                Path out = destination.resolve(entry.getName()).normalize();
                if (!out.startsWith(destination.normalize())) throw new IOException("Ruta insegura en ZIP de Gradle");
                if (entry.isDirectory()) {
                    Files.createDirectories(out);
                } else {
                    Files.createDirectories(out.getParent());
                    try (OutputStream stream = Files.newOutputStream(out)) {
                        byte[] buffer = new byte[65536];
                        int count;
                        while ((count = zip.read(buffer)) != -1) stream.write(buffer, 0, count);
                    }
                }
                zip.closeEntry();
            }
        }
    }

    private static boolean isWindows() {
        return System.getProperty("os.name", "").toLowerCase(java.util.Locale.ROOT).contains("win");
    }
}
