import React from 'react';
import { Container, Row, Col } from 'react-bootstrap';
import ApiTokenManagement from '../../components/ApiTokenManagement';
import ApiDocumentation from '../../components/ApiDocumentation';
function ApiTokens() {
  return (
    <Container fluid className="mt-4">
      <Row>
        <Col>
          <ApiTokenManagement />
          <ApiDocumentation />
        </Col>
      </Row>
    </Container>
  );
}

export default ApiTokens;