package io.slate.api.web;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Dashboard auth — deliberately NOT vibecoded (§13: hand-code the auth Clerk
 * used to own). These stubs pin the public contract; implement sign-up
 * (org + user + membership + bcrypt), login (JwtService.issueSession), and
 * API key issuance by hand, with tests, before onboarding design partners.
 */
@RestController
@RequestMapping("/auth")
public class AuthController {

    @PostMapping("/signup")
    public ResponseEntity<?> signup() {
        return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED)
                .body(Map.of("error", "signup not implemented yet"));
    }

    @PostMapping("/login")
    public ResponseEntity<?> login() {
        return ResponseEntity.status(HttpStatus.NOT_IMPLEMENTED)
                .body(Map.of("error", "login not implemented yet"));
    }
}
